from unittest.mock import patch

import pymupdf
import pytest

from core.document_processor import DocumentProcessor
from core.models import LexiRAGError
from core.ocr_engine import get_ocr
from config.settings import ROOT
from scripts.create_ocr_fixtures import create_fixtures


def test_genuine_rapidocr_scanned_mixed_and_incomplete_pages(settings, tmp_path):
    fixtures = create_fixtures(tmp_path / "fixtures")
    engine = get_ocr(str(ROOT / "data" / "ocr_models"))
    assert engine.health_check()["ready"]
    results = {}
    with patch("core.document_processor.get_ocr", return_value=engine):
        for name, path in fixtures.items():
            result = DocumentProcessor(settings).process(name, path.read_bytes())
            results[name] = result
            assert "thirty days" in " ".join(c.text for c in result.chunks).casefold()
            assert all(1 <= c.page <= result.pages for c in result.chunks)
            assert all(page["blocks"] for page in result.page_details)
    scanned = results["Scanned-Teaching.pdf"]
    assert scanned.scanned_pages == [1, 2]
    assert all(page["method"] == "rapidocr" for page in scanned.page_details)
    assert results["Mixed-Teaching.pdf"].page_details[0]["method"] == "native"
    assert results["Mixed-Teaching.pdf"].page_details[1]["method"] == "rapidocr"
    assert results["Incomplete-Text.pdf"].page_details[0]["method"] == "rapidocr"
    with pymupdf.open(fixtures["Scanned-Teaching.pdf"]) as pdf:
        assert not any(page.get_text().strip() for page in pdf)
    for page in scanned.page_details:
        assert all(0 <= b["bbox"][0] < b["bbox"][2] <= page["width"] + 1 and 0 <= b["bbox"][1] < b["bbox"][3] <= page["height"] + 1 for b in page["blocks"])


def test_one_failed_ocr_page_retains_native_pages_and_marks_warning(service, tmp_path):
    path = create_fixtures(tmp_path / "fixtures")["Mixed-Teaching.pdf"]
    with patch("core.document_processor.get_ocr") as mocked:
        mocked.return_value.recognize.side_effect = LexiRAGError("isolated OCR failure")
        result = service.upload(path.name, path.read_bytes())
    assert result["warnings"]
    assert service.db.document(result["id"])["status"] == "partial"
    assert {c.page for c in service.db.chunks()} == {1}
    assert service.db.page(result["id"], 2)["quality"] == "unreadable"
    duplicate = service.upload(path.name, path.read_bytes())
    assert duplicate["duplicate"] and duplicate["warnings"] == result["warnings"]
