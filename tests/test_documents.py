from unittest.mock import patch

import pymupdf
import pytest

from core.document_processor import DocumentProcessor
from core.models import LexiRAGError
from tests.conftest import make_pdf


def test_pages_locators_and_safe_names(settings):
    content = make_pdf(["Section 21 Privacy\nPrivacy is protected by informed consent in this teaching fixture.", "Article 14 Equality\nThis second page discusses equality in a teaching fixture."])
    result = DocumentProcessor(settings).process("../../legal.pdf", content)
    assert result.name == "legal.pdf"
    assert {c.page for c in result.chunks} == {1, 2}
    assert result.chunks[0].locator.startswith("Section 21")
    assert result.chunks[-1].locator.startswith("Article 14")
    assert all(c.document_id == result.document_id for c in result.chunks)


def test_section_not_invented_from_mid_sentence(settings):
    result = DocumentProcessor(settings).process("case.pdf", make_pdf(["The report refers to section 99 but does not contain a labeled provision."]))
    assert all(c.locator is None for c in result.chunks)


def test_long_text_chunks_stay_within_page(settings):
    result = DocumentProcessor(settings).process("long.pdf", make_pdf(["Privacy consent obligations. " * 65, "Termination notice duties. " * 50]))
    assert len(result.chunks) > 3
    assert all(len(c.text) <= settings.chunk_size for c in result.chunks)
    assert all("Termination" not in c.text for c in result.chunks if c.page == 1)


@pytest.mark.parametrize("name,content", [("bad.txt", b"%PDF-1.7"), ("bad.pdf", b"not a pdf"), ("damaged.pdf", b"%PDF-invalid")])
def test_invalid_pdf(settings, name, content):
    with pytest.raises(LexiRAGError):
        DocumentProcessor(settings).process(name, content)


def test_blank_pdf(settings):
    with pytest.raises(LexiRAGError, match="No readable text"):
        DocumentProcessor(settings).process("blank.pdf", make_pdf([""]))


def test_encrypted_pdf(settings):
    with pymupdf.open(stream=make_pdf(["Private legal document"]), filetype="pdf") as pdf:
        content = pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    with pytest.raises(LexiRAGError, match="Password"):
        DocumentProcessor(settings).process("locked.pdf", content)


def scanned_pdf():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 30))
        pix.clear_with(255)
        page.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=pix)
        return pdf.tobytes()


def test_scanned_pdf_detection_and_ocr_error(settings):
    content = scanned_pdf()
    with patch("core.document_processor.get_ocr") as ocr:
        ocr.return_value.recognize.return_value = ("", [])
        with pytest.raises(LexiRAGError, match="OCR"):
            DocumentProcessor(settings).process("scan.pdf", content)
        ocr.return_value.recognize.side_effect = RuntimeError("engine unavailable")
        with pytest.raises(LexiRAGError, match="Automatic OCR"):
            DocumentProcessor(settings).process("scan.pdf", content, use_ocr=True)


def test_page_and_size_limits(settings):
    from dataclasses import replace
    with pytest.raises(LexiRAGError, match="1–1 pages"):
        DocumentProcessor(replace(settings, max_pdf_pages=1)).process("large.pdf", make_pdf(["one", "two"]))
    with pytest.raises(LexiRAGError, match="MB limit"):
        DocumentProcessor(settings).process("large.pdf", b"%PDF-" + b" " * (settings.max_upload_mb * 1024 * 1024))

