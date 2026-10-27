"""Verify two real E-Commerce Rules questions without ingesting or reindexing.

--live sends retrieved excerpts to the configured Gemini provider. The expected
statutory phrases below are test assertions, never part of production prompts.
"""
import argparse
import json
from pathlib import Path

import pymupdf

from backend.container import Services
from core.citation_manager import normalize
from core.legal_sections import LegalIndex
from core.models import SearchFilters
from core.retrieval_diagnostics import configure
from backend.serialization import decode_result

QUESTION = "Under the Consumer Protection (E-Commerce) Rules, 2020, what is the time limit for acknowledging and resolving consumer complaints? Explain the relevant rule and provide citations from the uploaded document."
CONTROL = "Under the Consumer Protection (E-Commerce) Rules, 2020, may consent be recorded automatically using pre-ticked checkboxes? Explain the relevant rule and cite the uploaded document."


def verify(args):
    services = Services()
    configure(services.settings.data_dir)
    try:
        rules = services.corpus.db.document(args.document) if args.document else next(
            d for d in services.corpus.db.documents() if "e-commerce" in d["name"].lower() and "rules" in d["name"].lower())
        workspace = args.workspace or next(w["id"] for w in services.workspaces.list() if rules["id"] in services.workspaces.document_ids(w["id"]))
        filters = services.research.filters(workspace)
        chunks = services.corpus.db.chunks(SearchFilters(document_ids=(rules["id"],)))
        index = LegalIndex(services.corpus.db, chunks)
        provision_ids = index.by_reference.get("rule:4(5)", [])
        assert provision_ids, "Rule 4(5) is not structurally present in the indexed PDF"
        _, faiss_ids = services.corpus.vectors.load()
        assert set(provision_ids) <= set(faiss_ids)
        expected = " ".join(normalize(index.chunks[i].text) for i in provision_ids)
        assert "one month from the date of receipt" in expected and "eight hours" in expected
        results = {"workspace":workspace,"rules_id":rules["id"],"provision_ids":provision_ids,
                   "sqlite_faiss_and_ocr_complete":True,"questions":[]}
        for question, wanted_rule in [(QUESTION,"4(5)"),(CONTROL,"4(9)")]:
            hits = services.corpus.retriever.retrieve(question,filters=filters)
            entry = {"question":question,"hits":[{"id":h.chunk.id,"document_id":h.chunk.document_id,"page":h.chunk.page,
                      "locator":h.chunk.locator,"scores":h.scores} for h in hits]}
            if wanted_rule == "4(5)":
                assert any(h.chunk.id in provision_ids for h in hits), "Complete Rule 4(5) missing from initial evidence"
                assert hits[0].chunk.id in provision_ids, "Rule 4(5) did not rank first"
            if args.live or args.from_saved:
                if args.from_saved:
                    saved = next(r for r in services.workspaces.runs(workspace,200) if r["question"].strip()==question)
                    run_id, result = saved["id"], decode_result(saved["result_json"])
                else:
                    run_id, result = services.research.ask(workspace,question)
                assert not result.answer.insufficient_evidence, "Actual Gemini answer still reports insufficient evidence"
                statements = " ".join(f.heading+" "+f.statement for f in result.answer.findings).lower().replace(" ","")
                if wanted_rule=="4(5)":
                    assert wanted_rule in statements
                else:
                    assert any("Rule 4(9)" in (result.sources[ref.source_id].chunk.locator or "")
                               for f in result.answer.findings for ref in f.evidence)
                quotes=[]
                cited_pages=set()
                for finding in result.answer.findings:
                    for ref in finding.evidence:
                        hit=result.sources[ref.source_id]
                        stored=services.corpus.db.chunk(hit.chunk.id)
                        assert stored and stored.document_id==rules["id"] and stored.page==hit.chunk.page
                        assert normalize(ref.quote) in normalize(stored.text)
                        cited_pages.add(stored.page)
                        if stored.page==4:
                            quotes.append(normalize(ref.quote).lower())
                        if wanted_rule in finding.statement.replace(" ",""):
                            assert any(result.sources[r.source_id].chunk.page==4 for r in finding.evidence)
                joined=" ".join(quotes)
                if wanted_rule=="4(5)":
                    assert "48" in statements or "forty-eight" in statements
                    assert "onemonth" in statements or "1month" in statements
                    assert "eight hours" in joined and "one month" in joined
                else:
                    assert "pre-ticked" in joined and ("no such entity" in joined or "shall only record" in joined)
                entry.update(run_id=run_id,answer=result.answer.model_dump(),citation_valid=result.citation_valid,
                             citation_attempts=result.citation_attempts,verified_pdf_page=4,cited_pdf_pages=sorted(cited_pages))
            results["questions"].append(entry)
        with pymupdf.open(services.corpus.pdf_path(rules["id"])) as original:
            assert len(original)==rules["pages"]
            original[3].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(args.output.parent/"verified-original-page-4.png")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps({"sqlite_faiss_and_ocr_complete":True,"live":args.live,"verified_saved_live_runs":args.from_saved,
                          "question_results":[{"rule":"4(5)" if i==0 else "4(9)","top_page":e["hits"][0]["page"],
                                               "citation_valid":e.get("citation_valid"),"citation_attempts":e.get("citation_attempts")}
                                              for i,e in enumerate(results["questions"])],"output":str(args.output)},indent=2))
    finally:
        services.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live",action="store_true")
    parser.add_argument("--from-saved",action="store_true",help="Verify the latest persisted real-provider answers instead of making new requests")
    parser.add_argument("--document")
    parser.add_argument("--workspace")
    parser.add_argument("--output",type=Path,default=Path("data/rule45-validation/live-results.json"))
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    verify(args)
