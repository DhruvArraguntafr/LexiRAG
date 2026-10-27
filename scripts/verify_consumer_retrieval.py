"""Opt-in regression against the actual indexed Act; no ingestion or reset.

python -m scripts.verify_consumer_retrieval --workspace ID --document ACT_ID --live
The question/expected clauses belong only to this verification script, not RAG.
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

QUESTION = "What are the six consumer rights under the Consumer Protection Act, 2019? Explain them in simple language and cite the relevant section."
EXPECTED = ["hazardous to life and property", "quality, quantity, potency, purity",
            "competitive prices", "right to be heard", "seek redressal", "consumer awareness"]


def verify(args):
    services = Services()
    configure(services.settings.data_dir)
    try:
        services.workspaces.assert_document(args.workspace, args.document)
        scope = services.research.filters(args.workspace)
        act_chunks = services.corpus.db.chunks(SearchFilters(document_ids=(args.document,)))
        index = LegalIndex(services.corpus.db, act_chunks)
        ids = index.by_reference.get("section:2(9)", [])
        assert ids, "The indexed Act has no verifiable Section 2(9) passages"
        _, vector_ids = services.corpus.vectors.load()
        assert set(ids) <= set(vector_ids), "Provision chunk missing from FAISS"
        stored = " ".join(normalize(index.chunks[i].text).lower() for i in ids)
        assert all(phrase in stored for phrase in EXPECTED)
        hits = services.corpus.retriever.retrieve(QUESTION, filters=scope)
        text = " ".join(normalize(h.chunk.text).lower() for h in hits)
        assert all(phrase in text for phrase in EXPECTED), "Initial automatic retrieval lost a list item"
        payload = {"question": QUESTION, "workspace_id": args.workspace, "act_id": args.document,
                   "sqlite_and_faiss_provision_ids": ids, "all_six_in_initial_retrieval": True,
                   "hits": [{"id": h.chunk.id, "document_id": h.chunk.document_id,
                             "page": h.chunk.page, "locator": h.chunk.locator, "scores": h.scores} for h in hits]}
        if args.live:
            run_id, result = services.research.ask(args.workspace, QUESTION)
            assert not result.answer.insufficient_evidence, "Gemini still refused the real indexed Act"
            quotes = []
            with pymupdf.open(services.corpus.pdf_path(args.document)) as original:
                for finding in result.answer.findings:
                    for ref in finding.evidence:
                        hit = result.sources[ref.source_id]
                        assert normalize(ref.quote) in normalize(hit.chunk.text)
                        if hit.chunk.document_id == args.document:
                            assert normalize(ref.quote) in normalize(original[hit.chunk.page - 1].get_text("text", sort=True))
                            quotes.append(normalize(ref.quote).lower())
            assert all(any(phrase in quote for quote in quotes) for phrase in EXPECTED)
            statements = " ".join(f.statement for f in result.answer.findings).lower()
            assert "2(9)" in statements or "2 (9)" in statements or any("2(9)" in f.heading for f in result.answer.findings)
            # The content and verbatim support determine completeness, rather
            # than assuming the model always chooses six JSON finding objects.
            concepts = [r"hazard|safe|protect", r"inform|quality|price", r"choic|variety|competitive",
                        r"heard|hear|voice", r"redress|remed|complaint|exploit", r"awareness|aware|educat"]
            import re
            assert all(re.search(pattern, statements) for pattern in concepts)
            payload.update(live_gemini_passed=True, run_id=run_id,
                           answer=result.answer.model_dump(), citation_attempts=result.citation_attempts,
                           citation_valid=result.citation_valid)
            # Negative control uses the same real library and model, with the
            # actual Act excluded. Recovery must not silently re-include it.
            other_ids = [i for i in services.workspaces.document_ids(args.workspace) if i != args.document]
            if other_ids:
                negative_filters = services.research.filters(args.workspace, selected=other_ids)
                rejected = services.research.pipeline.research(QUESTION, filters=negative_filters)
                assert all(h.chunk.document_id in other_ids for h in rejected.sources.values())
                assert rejected.answer.insufficient_evidence
                payload.update(filtered_negative_control_passed=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"all_six_in_initial_retrieval": True,
                          "live_gemini_passed": payload.get("live_gemini_passed", False),
                          "citation_valid": payload.get("citation_valid"),
                          "filtered_negative_control_passed": payload.get("filtered_negative_control_passed"),
                          "evidence_pages": sorted({h.chunk.page for h in hits if h.chunk.document_id == args.document}),
                          "output": str(args.output)}, indent=2))
    finally:
        services.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--document", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/retrieval-fix-validation/real-act-results.json"))
    verify(parser.parse_args())
