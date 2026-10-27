import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field, model_validator

from core.models import LexiRAGError, SearchFilters
from core.rag_pipeline import RAGPipeline
from core.service import CorpusService
from evaluation.metrics import mean_measured, precision_at_k, recall_at_k, reciprocal_rank


class EvaluationCase(BaseModel):
    id: str
    question: str = Field(min_length=1, max_length=6000)
    relevant_chunk_ids: list[str]
    unsupported: bool = False
    document_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_labels(self):
        if self.unsupported and self.relevant_chunk_ids:
            raise ValueError("Unsupported questions must have no relevant chunks.")
        if not self.unsupported and not self.relevant_chunk_ids:
            raise ValueError("Supported questions need manually labeled relevant chunks.")
        return self


def load_dataset(content: str, service):
    try:
        cases = [EvaluationCase.model_validate_json(line) for line in content.splitlines() if line.strip()]
    except ValueError as exc:
        raise LexiRAGError("Invalid evaluation JSONL. Check the documented schema and labels.") from exc
    if not cases or len(cases) > 200:
        raise LexiRAGError("Use an evaluation dataset with 1–200 labeled questions.")
    if len({c.id for c in cases}) != len(cases):
        raise LexiRAGError("Evaluation case IDs must be unique.")
    chunks = {c.id: c for c in service.db.chunks()}
    documents = {d["id"] for d in service.db.documents()}
    for case in cases:
        if not set(case.relevant_chunk_ids) <= chunks.keys() or not set(case.document_ids) <= documents:
            raise LexiRAGError(f"Case {case.id}: unknown chunk/document IDs. Export current passage labels and update the dataset.")
        if case.document_ids and any(chunks[cid].document_id not in case.document_ids for cid in case.relevant_chunk_ids):
            raise LexiRAGError(f"Case {case.id}: relevance labels fall outside the document filter.")
    return cases


def run_experiment(service, dataset_text, k=6, modes=None, answers=False, ragas=False, progress=None, dataset_type="Unspecified / historical"):
    cases = load_dataset(dataset_text, service)
    modes = modes or ["semantic", "hybrid", "hybrid_rerank"]
    if not set(modes) <= {"semantic", "keyword", "hybrid", "hybrid_rerank"} or not modes:
        raise LexiRAGError("Unknown evaluation mode.")
    if ragas and not answers:
        raise LexiRAGError("Enable answer generation to evaluate faithfulness with Ragas.")
    if answers and not service.settings.api_key:
        raise LexiRAGError("GOOGLE_API_KEY is required for answer evaluation.")
    judge = None
    if ragas:
        from evaluation.answer_quality import AnswerQuality
        judge = AnswerQuality(service.settings)
    pipeline = RAGPipeline(service)
    revision = service.db.revision()
    rows = []
    for mode in modes:
        for i, case in enumerate(cases, 1):
            if progress:
                progress(f"{mode}: question {i}/{len(cases)}")
            start = perf_counter()
            hits = service.retriever.retrieve(case.question, k=k, mode="hybrid" if mode == "hybrid_rerank" else mode,
                                              rerank=mode == "hybrid_rerank", filters=SearchFilters(document_ids=tuple(case.document_ids)))
            retrieval_latency = perf_counter() - start
            ids = [h.chunk.id for h in hits]
            row = {"mode": mode, "case_id": case.id, "unsupported": case.unsupported,
                   "precision_at_k": precision_at_k(ids, case.relevant_chunk_ids, k) if not case.unsupported else None,
                   "recall_at_k": recall_at_k(ids, case.relevant_chunk_ids, k),
                   "mrr": reciprocal_rank(ids, case.relevant_chunk_ids), "retrieval_latency_seconds": retrieval_latency,
                   "response_latency_seconds": None, "rejected": None, "citation_provenance": None,
                   "citation_correctness": None, "answer_faithfulness": None, "retrieved_chunk_ids": ids}
            if answers:
                result = pipeline.from_sources(case.question, pipeline.select_sources(hits), mode=mode)
                row["response_latency_seconds"] = perf_counter() - start
                row["rejected"] = result.answer.insufficient_evidence and not result.answer.findings
                row["citation_provenance"] = result.citation_valid / result.citation_attempts if result.citation_attempts else None
                if judge:
                    row.update(judge.score(result))
            rows.append(row)
    if service.db.revision() != revision:
        raise LexiRAGError("Corpus changed during evaluation. Repeat with a stable document library.")
    aggregate = []
    metrics = ["precision_at_k", "recall_at_k", "mrr", "retrieval_latency_seconds", "response_latency_seconds",
               "citation_provenance", "citation_correctness", "answer_faithfulness"]
    for mode in modes:
        group = [r for r in rows if r["mode"] == mode]
        summary = {"mode": mode, **{metric: mean_measured([r[metric] for r in group]) for metric in metrics}}
        summary["unsupported_rejection_rate"] = mean_measured([r["rejected"] for r in group if r["unsupported"]])
        summary["supported_answer_rate"] = mean_measured([not r["rejected"] for r in group if not r["unsupported"] and r["rejected"] is not None])
        summary["question_count"] = len(group)
        aggregate.append(summary)
    payload = {"created_at": datetime.now(timezone.utc).isoformat(), "corpus_revision": revision, "dataset_type": dataset_type,
               "dataset_sha256": sha256(dataset_text.encode()).hexdigest(), "k": k,
               "embedding_model": service.settings.embedding_model, "reranker_model": service.settings.reranker_model,
               "gemini_model": service.settings.gemini_model if answers else None,
               "answer_evaluation": answers, "ragas": ragas, "summary": aggregate, "rows": rows,
               "notes": "Measured on supplied labels. First-use model loading is included in latency. Null means unmeasured or undefined. No question/answer/excerpt text stored."}
    destination = service.settings.results_dir / f"experiment-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    destination.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Run real retrieval and optional answer evaluation against an indexed LexiRAG corpus.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--modes", nargs="+", default=["semantic", "hybrid", "hybrid_rerank"])
    parser.add_argument("--answers", action="store_true", help="Send evidence to Gemini and measure rejection/provenance/latency")
    parser.add_argument("--ragas", action="store_true", help="Also judge faithfulness and citation support using Gemini/Ragas")
    args = parser.parse_args()
    try:
        result = run_experiment(CorpusService(), args.dataset.read_text(encoding="utf-8"), args.k, args.modes, args.answers, args.ragas, print)
        print(json.dumps(result["summary"], indent=2))
    except (LexiRAGError, OSError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")


if __name__ == "__main__":
    main()

