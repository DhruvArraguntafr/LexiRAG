from time import perf_counter
from dataclasses import replace
import re

from core.models import LexiRAGError, SearchFilters
from core.rag_pipeline import RAGPipeline
from core.document_comparison import DocumentComparator
from core.summarizer import DocumentSummarizer
from core.comparison_plan import is_comparison, resolve_comparison_documents

SEARCH_MODES = {
    "Fast search": {"k": 4, "mode": "semantic", "rerank": False},
    "Balanced search": {"k": 6, "mode": "hybrid", "rerank": False},
    "Deep research": {"k": 12, "mode": "hybrid", "rerank": True},
}


class ResearchService:
    def __init__(self, workspaces, generator=None):
        self.workspaces, self.corpus = workspaces, workspaces.corpus
        self.pipeline = RAGPipeline(self.corpus, generator)

    def filters(self, workspace_id, selected=None, category=None, jurisdiction=None, date_from=None, date_to=None):
        allowed = self.workspaces.document_ids(workspace_id)
        if not allowed:
            raise LexiRAGError("Add indexed documents to this workspace first.")
        if selected and not set(selected) <= set(allowed):
            raise LexiRAGError("One selected source is outside this workspace.")
        return SearchFilters(tuple(selected or allowed), category, jurisdiction, date_from, date_to)

    def resolve(self, workspace_id, question, filters):
        if not question.strip() or len(question) > 6000:
            raise LexiRAGError("Enter a question of 1–6,000 characters.")
        history = self.workspaces.runs(workspace_id, 3)
        docs = [d for d in self.workspaces.documents(workspace_id) if d["id"] in filters.document_ids]
        catalog = "\n".join(f"{i}. {d['name']}" for i, d in enumerate(docs, 1))
        context = "Documents in the displayed source order:\n" + catalog
        if history and re.search(r"\b(that|this|it|other|second|first|those|same|above|what about)\b", question, re.I):
            previous = history[0]["question"]
            resolved = f"{question}\nPrevious USER question for reference resolution only: {previous[:1800]}\n{context}"
        else:
            resolved = question
        return resolved[:5900], context

    def ask(self, workspace_id, question, search_mode="Balanced search", selected=None, advanced=None, expanded=False):
        parameters = dict(SEARCH_MODES.get(search_mode, SEARCH_MODES["Balanced search"]))
        parameters.update(advanced or {})
        filters = self.filters(workspace_id, selected)
        # AI Research still supports questions spanning several documents.
        # Independent retrieval and paired citations prevent one source from
        # crowding the others out of the evidence context.
        if is_comparison(question) and len(filters.document_ids) >= 2:
            ids = resolve_comparison_documents(self.corpus.db, filters.document_ids, question)
            scoped = replace(filters, document_ids=ids)
            result = DocumentComparator(self.corpus, self.pipeline.generator).compare(
                ids, question, k=min(6, int(parameters["k"])),
                rerank=True if parameters.get("rerank") else None, filters=scoped)
            run_id = self.workspaces.record_run(workspace_id, question, question, result, "comparison")
            return run_id, result
        resolved, catalog = self.resolve(workspace_id, question, filters)
        ordinal = re.search(r"\b(first|second|third)\s+(document|judgment|judgement|act|agreement)\b", question, re.I)
        if ordinal and "compar" not in question.casefold():
            candidates = [d for d in self.workspaces.documents(workspace_id) if d["id"] in filters.document_ids]
            kind = ordinal.group(2).casefold()
            if kind in {"judgment", "judgement"}:
                candidates = [d for d in candidates if d["document_type"] == "Judgment"]
            elif kind == "act":
                candidates = [d for d in candidates if d["document_type"] == "Act / Statute"]
            elif kind == "agreement":
                candidates = [d for d in candidates if d["document_type"] == "Contract / Agreement"]
            index = {"first": 0, "second": 1, "third": 2}[ordinal.group(1).casefold()]
            if index >= len(candidates):
                raise LexiRAGError("That source position is not available in the current selection. Name or select the intended document.")
            filters = SearchFilters(document_ids=(candidates[index]["id"],))
        started = perf_counter()
        guidance = ("Present a short answer, relevant provisions, supporting explanation and limitations as concise findings. "
                    "Do not fill unsupported sections. " + ("Give an expanded analysis. " if expanded else "Be concise. ") +
                    "Resolve follow-up references using the task context below, but only source excerpts are evidence. " + catalog)
        result = self.pipeline.research(resolved, filters=filters, instruction=guidance, **parameters)
        result.question = question
        result.latency_seconds = perf_counter() - started
        self.corpus.db.record_activity("research", result.latency_seconds, result.mode, result.answer.insufficient_evidence)
        run_id = self.workspaces.record_run(workspace_id, question, resolved, result)
        return run_id, result

    def search(self, workspace_id, question, selected=None, mode="hybrid", k=10, rerank=False, **metadata):
        hits = self.corpus.retriever.retrieve(question, filters=self.filters(workspace_id, selected, **metadata), mode=mode, k=k, rerank=rerank)
        self.workspaces.activity(workspace_id, "search", question)
        return hits

    def summarize(self, workspace_id, doc_id):
        self.workspaces.assert_document(workspace_id, doc_id)
        result = DocumentSummarizer(self.corpus, self.pipeline.generator).summarize(doc_id)
        identifier = self.workspaces.record_run(workspace_id, result.question, result.question, result, "summary")
        return identifier, result

    @staticmethod
    def quality(result):
        quotes = [" ".join(ref.quote.split()).casefold() for finding in result.answer.findings for ref in finding.evidence]
        return {
            "citation_provenance": f"{result.citation_valid}/{result.citation_attempts} attempted references verified",
            "duplicate_quotes": len(quotes) - len(set(quotes)),
            "interpretations": sum(f.kind == "interpretation" for f in result.answer.findings),
            "short_support": sum(len(q) < 35 for q in quotes),
            "potential_caveat_sources": ", ".join(sid for sid, hit in result.sources.items() if re.search(r"\b(except|unless|notwithstanding|subject to|provided that)\b", hit.chunk.text, re.I)) or "None flagged in retrieved excerpts; absence is not proof",
            "note": "These checks assist review; valid quotation provenance does not establish legal correctness or complete coverage of contrary evidence.",
        }
