"""Hierarchical map/reduce with provenance carried through verbatim excerpts."""
from dataclasses import replace
from time import perf_counter

from core.citation_manager import validate_answer
from core.models import LexiRAGError, SearchFilters, SearchHit
from core.rag_pipeline import RAGPipeline

SUMMARY_QUESTION = "Summarize the selected document: executive summary, important facts, main legal issues, relevant provisions, key findings and important dates."
SUMMARY_GUIDANCE = """Use the six requested headings when supported. Omit unsupported details and state what is missing.
Limit to at most 8 concise findings and at most two supporting excerpts per finding, each quote at most 240 characters.
Dates must be expressly present in the evidence; do not infer judgment or effective dates from upload dates.
This is a hierarchical document summary; evidence may cover only one group at an intermediate stage.
"""


class DocumentSummarizer:
    def __init__(self, service, generator=None):
        self.service, self.pipeline = service, RAGPipeline(service, generator)

    def _batches(self, sources):
        batch, size = {}, 0
        for sid, hit in sources.items():
            cost = len(hit.chunk.text) + len(hit.chunk.document_name) + 250
            if batch and size + cost > self.service.settings.context_chars:
                yield batch
                batch, size = {}, 0
            batch[sid], size = hit, size + cost
        if batch:
            yield batch

    def summarize(self, doc_id, progress=None):
        start = perf_counter()
        chunks = self.service.db.chunks(SearchFilters(document_ids=(doc_id,)))
        if not chunks:
            raise LexiRAGError("The selected document has no indexed passages.")
        original = {f"S{i}": SearchHit(chunk) for i, chunk in enumerate(chunks, 1)}
        current = original
        stage = 0
        while True:
            batches = list(self._batches(current))
            if progress:
                progress(f"Summary stage {stage + 1}: processing {len(batches)} evidence group(s)")
            if len(batches) == 1:
                result = self.pipeline.from_sources(SUMMARY_QUESTION, batches[0], SUMMARY_GUIDANCE, mode="summary")
                break
            next_sources = {}
            for i, batch in enumerate(batches, 1):
                if progress:
                    progress(f"Summary stage {stage + 1}: group {i}/{len(batches)}")
                mapped = self.pipeline.from_sources(SUMMARY_QUESTION, batch, SUMMARY_GUIDANCE, mode="summary-map")
                for finding in mapped.answer.findings[:8]:
                    for ref in finding.evidence[:2]:
                        # A verbatim sub-excerpt remains grounded in the original page.
                        quote = ref.quote[:240]
                        source = original[ref.source_id]
                        existing = next_sources.get(ref.source_id)
                        text = existing.chunk.text + "\n" + quote if existing else quote
                        next_sources[ref.source_id] = SearchHit(replace(source.chunk, text=text))
            if not next_sources:
                result = self.pipeline.from_sources(SUMMARY_QUESTION, {}, mode="summary")
                break
            old_cost = sum(len(h.chunk.text) + 250 for h in current.values())
            new_cost = sum(len(h.chunk.text) + 250 for h in next_sources.values())
            if new_cost >= old_cost or stage >= 8:
                raise LexiRAGError("Summary evidence could not be reduced within the context budget. Increase LLM_CONTEXT_CHARS and retry.")
            current = next_sources
            stage += 1
        # Expose original passages and validate again against originals, never map prose.
        result.sources = {sid: original[sid] for sid in result.sources}
        result.answer, result.citation_attempts, result.citation_valid = validate_answer(result.answer, result.sources)
        result.answer.limitations.append(
            f"Processed {len(chunks)} chunks across {len({c.page for c in chunks})} text-bearing PDF pages using {stage + 1} summary stage(s). "
            "Hierarchical compression can omit detail; inspect original sources."
        )
        doc = self.service.db.document(doc_id)
        if doc and doc["warnings"] != "[]":
            result.answer.limitations.append("Extraction warnings exist for this document; review them in the library. Image-only or unreadable text may be missing.")
        result.latency_seconds = perf_counter() - start
        self.service.db.record_activity("summary", result.latency_seconds, "hierarchical", result.answer.insufficient_evidence)
        return result

