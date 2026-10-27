"""Opt-in real Gemini comparison checks on the existing, unchanged library.

Uses frozen questions through AI Research, including paired citation coverage.
Saves actual answers, provenance checks, latency and partial results privately.
"""
import argparse
import json
import traceback
from pathlib import Path

from backend.container import Services
from core.citation_manager import normalize
from core.document_comparison import comparison_coverage
from core.retrieval_diagnostics import configure
from scripts.evaluate_crossdoc import cases


def main(args):
    services=Services()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # A separate verifier log avoids Windows rotation conflicts with the
    # running application's private diagnostic file.
    configure(args.output.parent)
    payload={"model":services.settings.gemini_model,"results":[]}
    try:
        dataset,questions=cases(services,args.dataset)
        for case in questions:
            workspace=next(w["id"] for w in services.workspaces.list()
                           if set(case["document_ids"])<=set(services.workspaces.document_ids(w["id"])))
            row={"case":case["id"],"route":"research","question":case["question"]}
            try:
                run,result=services.research.ask(workspace,case["question"],selected=case["document_ids"])
                complete,cited,paired,invalid=comparison_coverage(result,case["document_ids"])
                provenance=True
                for finding in result.answer.findings:
                    for ref in finding.evidence:
                        chunk=result.sources[ref.source_id].chunk
                        stored=services.corpus.db.chunk(chunk.id)
                        provenance=provenance and bool(stored and stored.document_id in case["document_ids"]
                            and stored.document_id==chunk.document_id and stored.page==chunk.page
                            and normalize(ref.quote) in normalize(stored.text))
                row.update(run_id=run,complete=complete,paired_findings=paired,cited_documents=sorted(cited),
                    provenance_verified=provenance,citation_valid=result.citation_valid,
                    citation_attempts=result.citation_attempts,latency_seconds=result.latency_seconds,
                    answer=result.answer.model_dump(),sources={sid:{"id":h.chunk.id,
                    "document":h.chunk.document_name,"document_id":h.chunk.document_id,
                    "page":h.chunk.page,"locator":h.chunk.locator} for sid,h in result.sources.items()})
            except Exception as exc:
                # Provider exception text can contain private prompts: type only.
                row.update(complete=False,error_type=type(exc).__name__,error_frames=[
                    {"file":Path(frame.filename).name,"line":frame.lineno,"function":frame.name}
                    for frame in traceback.extract_tb(exc.__traceback__)])
            payload["results"].append(row)
            args.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
            print(json.dumps({key:value for key,value in row.items() if key not in {"question","answer","sources","run_id"}}),flush=True)
        case=questions[0]
        workspace=next(w["id"] for w in services.workspaces.list()
                       if set(case["document_ids"])<=set(services.workspaces.document_ids(w["id"])))
        _,negative=services.research.ask(workspace,dataset["negative_question"],selected=case["document_ids"])
        payload["unsupported_control"]={"question":dataset["negative_question"],
            "rejected":negative.answer.insufficient_evidence,"findings":len(negative.answer.findings),
            "answer":negative.answer.model_dump()}
        args.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({"unsupported_control":payload["unsupported_control"]["rejected"]}),flush=True)
    finally:
        services.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true",required=True,help="Explicitly send selected excerpts to configured Gemini")
    parser.add_argument("--dataset",type=Path,default=Path("evaluation/crossdoc_questions.json"))
    parser.add_argument("--output",type=Path,default=Path("data/cross-document-validation/live-results.json"))
    main(parser.parse_args())
