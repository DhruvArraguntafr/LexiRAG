"""Check history, citations and exports in an isolated COPY of a real library.

--live also asks Gemini about an explicit provision in the copied corpus.
Never point this at the main library: live runs are persisted in the copy.
"""
import argparse
import json
from pathlib import Path

import pymupdf

from backend.container import Services
from backend.serialization import decode_result, encode_result
from config.settings import Settings
from core.citation_manager import normalize
from core.models import LexiRAGError
from utils.reports import report_pdf, markdown_pdf


def check(args):
    services = Services(Settings(data_dir=args.data_dir.resolve()))
    results = {"decoded_history": 0, "readable_history": 0, "stale_history_blocked": 0,
               "valid_findings": 0, "exported_reports": 0, "stale_reports_blocked": 0}
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        for workspace in services.workspaces.list():
            identifier = workspace["id"]
            for row in services.workspaces.runs(identifier, limit=100000):
                decoded = decode_result(row["result_json"])
                assert encode_result(decode_result(encode_result(decoded))) == encode_result(decoded)
                results["decoded_history"] += 1
                try:
                    services.workspaces.run(identifier, row["id"])
                except LexiRAGError as exc:
                    assert "changed or were removed" in str(exc)
                    results["stale_history_blocked"] += 1
                else:
                    results["readable_history"] += 1
            results["valid_findings"] += sum(f["valid_sources"] for f in services.evidence.findings(identifier))
            for report in services.briefs.list(identifier):
                try:
                    text = services.briefs.export(identifier, report["id"])
                except LexiRAGError as exc:
                    assert "sources have changed" in str(exc)
                    results["stale_reports_blocked"] += 1
                else:
                    content = markdown_pdf(text, report["title"])
                    with pymupdf.open(stream=content, filetype="pdf") as pdf:
                        assert len(pdf) > 0
                    results["exported_reports"] += 1

        if args.live:
            document = next(d for d in services.corpus.db.documents() if "Direct Selling" in d["name"])
            workspace = next(w["id"] for w in services.workspaces.list()
                             if document["id"] in services.workspaces.document_ids(w["id"]))
            question = ("Under Rule 5(7) of the Consumer Protection (Direct Selling) Rules, 2021, "
                        "what are the time limits for acknowledging and resolving consumer complaints? "
                        "Name the rule and cite the uploaded document.")
            _, result = services.research.ask(workspace, question, selected=[document["id"]])
            assert result.answer.findings and not result.answer.insufficient_evidence
            assert result.citation_valid == result.citation_attempts > 0
            for finding in result.answer.findings:
                for ref in finding.evidence:
                    chunk = result.sources[ref.source_id].chunk
                    assert chunk.document_id == document["id"]
                    assert normalize(ref.quote) in normalize(services.corpus.db.chunk(chunk.id).text)
            statements = " ".join(f.heading + " " + f.statement for f in result.answer.findings).casefold()
            assert "5(7)" in statements
            assert "48" in statements or "forty-eight" in statements
            assert "month" in statements
            content = report_pdf(result)
            (args.output / "real-provision-report.pdf").write_bytes(content)
            results["live_legal_provision"] = {"rule": "5(7)", "verified_citations": result.citation_valid,
                                              "pages": sorted({h.chunk.page for h in result.sources.values()})}
        (args.output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        services.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    check(parser.parse_args())
