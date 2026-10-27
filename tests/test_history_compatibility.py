"""Old comparison records remain usable after removing their dedicated screen."""
from backend.container import Services
from backend.serialization import decode_result, encode_result
from core.document_comparison import DocumentComparator
from tests.conftest import ExtractiveTestGenerator
from utils.reports import report_markdown, report_pdf

import pymupdf


def test_historical_comparison_survives_restart_save_and_export(populated):
    services = Services(populated.settings, populated.embeddings, ExtractiveTestGenerator())
    try:
        workspace = services.workspaces.create("Existing history")
        ids = [d["id"] for d in services.corpus.db.documents()]
        for identifier in ids:
            services.workspaces.attach(workspace, identifier)
        result = DocumentComparator(services.corpus, ExtractiveTestGenerator()).compare(
            ids, "Compare privacy and notice")
        run = services.workspaces.record_run(workspace, result.question, result.question, result, "comparison")
        encoded = encode_result(result)
    finally:
        services.close()

    reopened = Services(populated.settings, populated.embeddings, ExtractiveTestGenerator())
    try:
        row, restored = reopened.workspaces.run(workspace, run)
        assert row["kind"] == "comparison"
        assert encode_result(restored) == encoded
        assert decode_result(encoded).comparison_rows == result.comparison_rows
        reopened.evidence.save_finding(workspace, run, 0)
        assert reopened.evidence.findings(workspace)[0]["valid_sources"]
        assert "Comparison findings" in report_markdown(restored)
        with pymupdf.open(stream=report_pdf(restored), filetype="pdf") as pdf:
            assert "Comparison findings" in " ".join(page.get_text() for page in pdf)
    finally:
        reopened.close()
