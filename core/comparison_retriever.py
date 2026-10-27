"""Independent multi-query retrieval with document/concept coverage and context."""
from dataclasses import dataclass, replace
import logging
import math

from core.comparison_plan import ComparisonPlan, document_aliases, plan_comparison
from core.embeddings import load_reranker
from core.hybrid_retriever import reciprocal_rank_fusion
from core.models import SearchFilters, SearchHit, LexiRAGError
from core.retrieval_diagnostics import record

# The small frozen retrieval experiment supported automatic reranking for
# comparisons. Individual questions can still regress; retain
# scoped hybrid fallback when the optional local model is unavailable.
AUTO_RERANK = True


@dataclass
class ComparisonEvidence:
    plan: ComparisonPlan
    anchors: dict[str, list[SearchHit]]
    groups: dict[str, list[SearchHit]]
    reranked: bool


class ComparisonRetriever:
    def __init__(self, corpus):
        self.corpus=corpus

    def retrieve(self, document_ids, question, k=4, rerank=None, expanded=False, filters=None, recover_weak=True):
        ids=list(dict.fromkeys(document_ids))
        if not 2<=len(ids)<=8 or not 1<=k<=12:
            raise LexiRAGError("Choose two to eight documents and a valid evidence limit.")
        aliases=[]
        for identifier in ids:
            doc=self.corpus.db.document(identifier)
            if not doc:
                raise LexiRAGError("A selected PDF is unavailable. Refresh your selection.")
            if filters and filters.document_ids and identifier not in filters.document_ids:
                raise LexiRAGError("A selected PDF is outside the allowed research documents.")
            aliases.extend(document_aliases(self.corpus.db,doc))
        plan=plan_comparison(question,aliases)
        queries=list(plan.concepts)
        if expanded:
            queries=list(dict.fromkeys([*queries,*plan.expanded]))[:8]
        use_reranker=AUTO_RERANK if rerank is None else rerank
        anchors,groups={},{}
        weak_documents=[]
        ran_reranker=False
        for identifier in ids:
            document_reranked=False
            scope=replace(filters or SearchFilters(),document_ids=(identifier,))
            candidates,rankings={},[]
            exact_ids=set()
            for query in queries:
                hits=self.corpus.retriever.retrieve(query,k=min(12,max(k*2,8)),mode="hybrid",filters=scope)
                exact_ids.update(h.chunk.id for h in hits if h.scores.get("exact_reference"))
                candidates.update((h.chunk.id,h) for h in hits)
                rankings.append([(h.chunk.id,1.0) for h in hits])
            for chunk_id in exact_ids:
                candidates[chunk_id].scores["exact_reference"]=1.0
            fused=reciprocal_rank_fusion(rankings)
            pool=[candidates[i] for i,_ in fused[:32]]
            concept_orders=[]
            if use_reranker and pool:
                try:
                    model=load_reranker(self.corpus.settings.reranker_model,str(self.corpus.settings.model_cache))
                    for concept in plan.concepts:
                        values=model.predict([(concept,h.chunk.text) for h in pool],show_progress_bar=False)
                        if len(values)!=len(pool) or not all(math.isfinite(float(v)) for v in values):
                            raise ValueError("Invalid local reranker scores")
                        order=sorted(zip(pool,values),key=lambda pair:float(pair[1]),reverse=True)
                        concept_orders.append([h.chunk.id for h,_ in order])
                        for hit,score in order:
                            hit.scores["reranker_logit"]=max(hit.scores.get("reranker_logit",float("-inf")),float(score))
                    ran_reranker=True
                    document_reranked=True
                except Exception as exc:
                    # Keep a working scoped hybrid search if an optional model
                    # cannot load. Do not expose document text/provider errors.
                    logging.getLogger("lexirag.retrieval").warning("Comparison reranking unavailable (%s)",type(exc).__name__)
                    concept_orders=[]
                    for hit in pool:
                        hit.scores.pop("reranker_logit",None)
            if not concept_orders:
                concept_orders=[[i for i,_ in ranking] for ranking in rankings[:len(plan.concepts)]]
            combined=reciprocal_rank_fusion([[(i,1.0) for i in order] for order in concept_orders])
            # One best anchor per concept before filling the remaining slots.
            exact=[i for i,_ in fused if i in exact_ids]
            order=list(dict.fromkeys(exact+[o[0] for o in concept_orders if o]+[i for i,_ in combined]+[i for i,_ in fused]))
            chosen=[candidates[i] for i in order[:k] if i in candidates]
            anchors[identifier]=chosen
            logits=[h.scores["reranker_logit"] for h in chosen if "reranker_logit" in h.scores]
            # This is a search-expansion hint, not a calibrated probability or
            # a reason to reject evidence. Negative local relevance scores on
            # most anchors warrant another bounded, scoped candidate search.
            if document_reranked and len(logits)>=2 and sum(s<0 for s in logits)>len(logits)/2:
                weak_documents.append(identifier)
            if expanded and chosen:
                recovery=self.corpus.retriever.broaden(" ".join(plan.concepts),scope,chosen,k=16)
            else:
                recovery=[]
            # Attach only nearby passage/provision context; never replace an
            # anchor with a whole Definitions section or cross document scope.
            with self.corpus.lock():
                chunks=self.corpus.db.chunks(scope)
                structure=self.corpus.retriever.legal_index(chunks)
                neighbors=[]
                for hit in chosen:
                    refs=structure.labels.get(hit.chunk.id,set())
                    for chunk in chunks:
                        if chunk.id in {h.chunk.id for h in chosen}:
                            continue
                        overlap=refs & structure.labels.get(chunk.id,set())
                        if chunk.document_id==identifier and abs(chunk.ordinal-hit.chunk.ordinal)==1 and (
                            overlap or chunk.page==hit.chunk.page):
                            neighbors.append(SearchHit(structure.enrich(chunk),{"comparison_context":1.0}))
            additional=list(dict.fromkeys(h.chunk.id for h in [*neighbors,*recovery]))
            lookup={h.chunk.id:h for h in [*neighbors,*recovery]}
            groups[identifier]=chosen+[lookup[i] for i in additional if i not in {h.chunk.id for h in chosen}][:max(2,k)]
            record(question,scope,"comparison_document",groups[identifier],concepts=list(plan.concepts),
                   expanded=expanded,reranked=document_reranked)
        if weak_documents and not expanded and recover_weak:
            return self.retrieve(ids,question,k,rerank,expanded=True,filters=filters)
        return ComparisonEvidence(plan,anchors,groups,ran_reranker)


def balanced_sources(evidence, context_chars):
    """Reserve each selected document's context share, with anchors first."""
    groups=evidence.groups
    quota=context_chars//len(groups)
    selected={}
    for identifier,hits in groups.items():
        total=0
        selected[identifier]=[]
        for hit in hits:
            cost=len(hit.chunk.text)+len(hit.chunk.document_name)+250
            if total+cost>quota:
                if not selected[identifier] and quota>400:
                    available=quota-len(hit.chunk.document_name)-250
                    text=hit.chunk.text[:available].rsplit(" ",1)[0]
                    if len(text)>=80:
                        selected[identifier].append(SearchHit(replace(hit.chunk,text=text),dict(hit.scores)))
                        total+=len(text)+len(hit.chunk.document_name)+250
                continue
            selected[identifier].append(hit)
            total+=cost
    ordered=[hits[i] for i in range(max((len(v) for v in selected.values()),default=0)) for hits in selected.values() if i<len(hits)]
    return {f"S{i}":hit for i,hit in enumerate(ordered,1)}
