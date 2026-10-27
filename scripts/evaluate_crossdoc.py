"""Measured cross-document retrieval on predeclared, manually labelled questions.

The baseline artifact was captured before implementation. Live provider checks
are separate in scripts.verify_crossdoc; no scores are simulated.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

from backend.container import Services
from core.models import SearchFilters


def cases(services, path):
    dataset=json.loads(path.read_text(encoding="utf-8"))
    docs=services.corpus.db.documents()
    chunks=services.corpus.db.chunks()
    result=[]
    for case in dataset["cases"]:
        item=dict(case)
        item["document_ids"]=[next(d["id"] for d in docs if d["id"].startswith(p)) for p in case["document_prefixes"]]
        item["relevant_ids"]=[next(c.id for c in chunks if c.id.startswith(p)) for p in case["relevant_prefixes"]]
        assert set(item["relevant_ids"]) <= {c.id for c in chunks if c.document_id in item["document_ids"]}
        result.append(item)
    return dataset,result


def metrics(hits, case, k):
    relevant=set(case["relevant_ids"])
    if not relevant:
        raise ValueError("Retrieval evaluation needs nonempty manual relevance labels; generation-only holdouts have none.")
    selected=hits[:k*len(case["document_ids"]) ]
    good=[h for h in selected if h.chunk.id in relevant]
    rr=[]
    for doc in case["document_ids"]:
        doc_hits=[h for h in selected if h.chunk.document_id==doc][:k]
        rr.append(next((1/r for r,h in enumerate(doc_hits,1) if h.chunk.id in relevant),0))
    return {"precision":len(good)/(k*len(case["document_ids"])),
            "recall":len({h.chunk.id for h in good})/len(relevant),
            "mrr_per_document":sum(rr)/len(rr),
            "document_coverage":len({h.chunk.document_id for h in selected})/len(case["document_ids"]),
            "relevant_document_coverage":len({h.chunk.document_id for h in good})/len(case["document_ids"])}


def main(args):
    services=Services()
    try:
        dataset,questions=cases(services,args.dataset)
        if args.warmup:
            from core.embeddings import load_reranker
            services.corpus.embeddings.embed_query("retrieval warmup")
            load_reranker(services.settings.reranker_model,str(services.settings.model_cache)).predict(
                [("retrieval warmup","A passage for initializing the local model.")],show_progress_bar=False)
        k=dataset["k_per_document"]
        results=[]
        for case in questions:
            methods=["global_hybrid","planned_hybrid","planned_reranked","automatic_comparison"]
            for method in methods:
                start=perf_counter()
                if method=="global_hybrid":
                    hits=services.corpus.retriever.retrieve(case["question"],k=k*len(case["document_ids"]),filters=SearchFilters(document_ids=tuple(case["document_ids"])))
                else:
                    from core.comparison_retriever import ComparisonRetriever
                    retrieval=ComparisonRetriever(services.corpus).retrieve(case["document_ids"],case["question"],k=k,
                        rerank=method!="planned_hybrid",recover_weak=method=="automatic_comparison")
                    hits=[h for group in retrieval.anchors.values() for h in group]
                elapsed=perf_counter()-start
                row={"case":case["id"],"method":method,"latency_seconds":elapsed,
                     **metrics(hits,case,k),"ids":[h.chunk.id for h in hits],
                     "scores":[h.scores for h in hits]}
                results.append(row)
                print(json.dumps({key:value for key,value in row.items() if key not in {"ids","scores"}},ensure_ascii=True),flush=True)
        payload={"dataset":str(args.dataset),"k_per_document":k,"models_warmed":args.warmup,"results":results}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    finally:
        services.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup",action="store_true",help="Initialize both real local models before timing")
    parser.add_argument("--dataset",type=Path,default=Path("evaluation/crossdoc_questions.json"))
    parser.add_argument("--output",type=Path,default=Path("data/cross-document-validation/retrieval.json"))
    main(parser.parse_args())
