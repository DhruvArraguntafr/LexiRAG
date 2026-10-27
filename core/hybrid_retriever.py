from collections import defaultdict

from filelock import FileLock

from core.embeddings import load_reranker
from core.keyword_search import keyword_search
from core.models import LexiRAGError, SearchFilters, SearchHit
from core.legal_sections import LegalIndex, query_variants, references, named_documents
from core.retrieval_diagnostics import record


def reciprocal_rank_fusion(rankings, constant=60):
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, (chunk_id, _) in enumerate(ranking, 1):
            scores[chunk_id] += 1.0 / (constant + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


class HybridRetriever:
    def __init__(self, database, vectors, embeddings, settings):
        self.db, self.vectors, self.embeddings, self.settings = database, vectors, embeddings, settings
        self._legal_key, self._legal = None, None

    def legal_index(self, chunks):
        key = (self.db.revision(), tuple(sorted({c.document_id for c in chunks})))
        if key != self._legal_key:
            self._legal = LegalIndex(self.db, chunks)
            self._legal_key = key
        return self._legal

    def retrieve(self, question, k=6, mode="hybrid", filters=None, rerank=False):
        question = question.strip()
        if not question or len(question) > 6000:
            raise LexiRAGError("Enter a question between 1 and 6,000 characters.")
        if mode not in {"semantic", "keyword", "hybrid"} or not 1 <= k <= 30:
            raise LexiRAGError("Select a valid retrieval mode and top-K between 1 and 30.")
        if filters and filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise LexiRAGError("The start date must precede the end date.")
        if filters:
            from datetime import date
            for value in (filters.date_from, filters.date_to):
                if value:
                    try:
                        if date.fromisoformat(value).isoformat() != value:
                            raise ValueError("Use canonical dates")
                    except ValueError as exc:
                        raise LexiRAGError("Use valid legal dates in YYYY-MM-DD format.") from exc
        with FileLock(str(self.settings.data_dir / "corpus.lock"), timeout=120):
            chunks = self.db.chunks(filters or SearchFilters())
            if not chunks:
                record(question, filters, "empty_scope", [])
                return []
            pool_size = min(len(chunks), max(k * 4, 20))
            semantic, keyword = [], []
            if mode != "keyword":
                semantic = self.vectors.search(self.embeddings.embed_query(question), chunks, pool_size)
            if mode != "semantic":
                keyword = keyword_search(question, chunks, pool_size)
            focused_semantic, focused_keyword = [], []
            if mode == "hybrid":
                variants = query_variants(question)
                focal = variants[0] if variants else question
                if focal.casefold() != question.casefold():
                    focused_semantic = self.vectors.search(self.embeddings.embed_query(focal), chunks, pool_size)
                    focused_keyword = keyword_search(focal, chunks, pool_size)
            legal, exact, definitions, protected = None, [], [], []
            if mode == "hybrid":
                legal = self.legal_index(chunks)
                exact, definitions = legal.lookup(question)
                protected = legal.related(exact or definitions, limit=k)
            rankings = semantic if mode == "semantic" else keyword if mode == "keyword" else reciprocal_rank_fusion(
                [semantic, keyword, focused_semantic, focused_keyword, [(identifier, 1.0) for identifier in exact + definitions]])
            rank_scores = dict(rankings)
            ordered = list(dict.fromkeys(protected + [identifier for identifier, _ in rankings]))
            chunk_map = {c.id: c for c in chunks}
            preferred_documents = named_documents(question, self.db.documents()) if mode == "hybrid" else set()
            if preferred_documents:
                ordered.sort(key=lambda identifier: chunk_map[identifier].document_id not in preferred_documents)
            semantic_scores, keyword_scores = dict(semantic), dict(keyword)
            focused_semantic_scores, focused_keyword_scores = dict(focused_semantic), dict(focused_keyword)
            results = []
            for chunk_id in ordered[:pool_size]:
                score = rank_scores.get(chunk_id, 0.0)
                scores = {mode if mode != "hybrid" else "rrf": score}
                if chunk_id in semantic_scores:
                    scores["cosine"] = semantic_scores[chunk_id]
                if chunk_id in keyword_scores:
                    scores["bm25"] = keyword_scores[chunk_id]
                if chunk_id in exact:
                    scores["exact_reference"] = 1.0
                if chunk_id in definitions:
                    scores["definition_heading"] = 1.0
                if chunk_id in protected:
                    scores["section_context"] = 1.0
                if chunk_id in focused_semantic_scores:
                    scores["focused_cosine"] = focused_semantic_scores[chunk_id]
                if chunk_id in focused_keyword_scores:
                    scores["focused_bm25"] = focused_keyword_scores[chunk_id]
                if chunk_map[chunk_id].document_id in preferred_documents:
                    scores["named_document"] = 1.0
                results.append(SearchHit(legal.enrich(chunk_map[chunk_id]) if legal else chunk_map[chunk_id], scores))
        if rerank and results:
            try:
                model = load_reranker(self.settings.reranker_model, str(self.settings.model_cache))
                scores = model.predict([(question, hit.chunk.text) for hit in results], show_progress_bar=False)
                for hit, score in zip(results, scores):
                    hit.scores["reranker_logit"] = float(score)
                results.sort(key=lambda h: h.scores["reranker_logit"], reverse=True)
            except Exception as exc:
                raise LexiRAGError("Reranker could not be loaded or run. Check its model ID/network, or disable reranking.") from exc
        results = results[:k]
        record(question, filters, "retrieve", results, requested_references=references(question),
               exact_reference_found=bool(exact), definition_found=bool(definitions))
        return results

    def broaden(self, question, filters=None, initial=None, k=24):
        """Bounded, scoped query expansion and provision/neighbor completion."""
        k = min(30, max(k, 12))
        initial = initial or []
        candidates = {h.chunk.id: h for h in initial}
        rankings = [[(h.chunk.id, 1.0) for h in initial]]
        for variant in list(dict.fromkeys([question, *query_variants(question)]))[:4]:
            hits = self.retrieve(variant, k=k, mode="keyword", filters=filters)
            candidates.update((h.chunk.id, h) for h in hits)
            rankings.append([(h.chunk.id, 1.0) for h in hits])
        with FileLock(str(self.settings.data_dir / "corpus.lock"), timeout=120):
            chunks = self.db.chunks(filters or SearchFilters())
            if not chunks:
                return []
            legal = self.legal_index(chunks)
            exact, definitions = legal.lookup(question)
            ranking = [(identifier, score) for identifier, score in reciprocal_rank_fusion(rankings) if identifier in legal.chunks]
            preferred_documents = named_documents(question, self.db.documents())
            if preferred_documents:
                ranking.sort(key=lambda pair: legal.chunks[pair[0]].document_id not in preferred_documents)
            seeds = exact or definitions or [identifier for identifier, _ in ranking[:4]]
            protected = legal.related(seeds, limit=k)
            # Adjacent stored chunks recover continuation text in judgments or
            # older imports without statutory headings. Scope never broadens.
            neighbors = []
            seed_chunks = [legal.chunks[i] for i in seeds[:4] if i in legal.chunks]
            for chunk in chunks:
                if any(chunk.document_id == seed.document_id and abs(chunk.ordinal - seed.ordinal) == 1 for seed in seed_chunks):
                    neighbors.append(chunk.id)
            order = list(dict.fromkeys(protected + neighbors + [i for i, _ in ranking]))
            if preferred_documents:
                order.sort(key=lambda identifier: legal.chunks[identifier].document_id not in preferred_documents)
            order = order[:k]
            scores = dict(ranking)
            hits = []
            for identifier in order:
                if identifier not in legal.chunks:
                    continue
                score = dict(candidates[identifier].scores) if identifier in candidates else {}
                score["recovery_rrf"] = scores.get(identifier, 0.0)
                hits.append(SearchHit(legal.enrich(legal.chunks[identifier]), score))
        record(question, filters, "expanded", hits, requested_references=references(question),
               exact_reference_found=bool(exact), definition_found=bool(definitions))
        return hits

