"""Automatic page inspection, native extraction, layout assistance and local OCR."""
from dataclasses import dataclass, field
from hashlib import sha256
import re

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import Settings
from core.models import Chunk, LexiRAGError
from core.ocr_engine import get_ocr
from core.legal_sections import SectionTracker, display


@dataclass
class ProcessedPDF:
    document_id: str
    name: str
    pages: int
    chunks: list[Chunk]
    warnings: list[str]
    scanned_pages: list[int]
    page_details: list[dict] = field(default_factory=list)


class DocumentProcessor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
            separators=["\n\n", "\n", ". ", "; ", " ", ""],
        )

    @staticmethod
    def sections(text: str):
        """Recognize only explicit, line-anchored section/article/paragraph labels."""
        pattern = re.compile(
            r"(?im)^\s*((?:section|article|paragraph|para\.?|clause)\s+\d+[A-Za-z]?(?:[.(]\d+\)?)?\b[^\n]{0,100}|\d{1,3}[.)]\s+[^\n]{8,100})"
        )
        matches = list(pattern.finditer(text))
        start, locator = 0, None
        for match in matches:
            if match.start() > start:
                yield locator, text[start:match.start()]
            start = match.start()
            label = match.group(1).strip()
            # Numbered paragraphs are identified only as explicit numbered blocks.
            locator = label if not label[0].isdigit() else "Numbered block " + label.split()[0]
        yield locator, text[start:]

    def process(self, name: str, content: bytes, use_ocr: bool | None = None, progress=None) -> ProcessedPDF:
        safe_name = name.replace("\\", "/").rsplit("/", 1)[-1]
        if not safe_name.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            raise LexiRAGError("Upload a valid PDF file with a .pdf extension.")
        if len(content) > self.settings.max_upload_mb * 1024 * 1024:
            raise LexiRAGError(f"PDF exceeds the {self.settings.max_upload_mb} MB limit.")
        doc_id = sha256(content).hexdigest()
        chunks, warnings, scanned, details = [], [], [], []
        tracker = SectionTracker("rule" if re.search(r"(?i)\brules?\b", safe_name) else None)
        def report(stage, completed=0, total=0, message=""):
            if progress:
                progress(stage, completed, total, message)
        report("Inspecting document")
        try:
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise LexiRAGError("Password-protected PDFs must be unlocked before uploading.")
                if not 0 < len(pdf) <= self.settings.max_pdf_pages:
                    raise LexiRAGError(f"PDF must contain 1–{self.settings.max_pdf_pages} pages.")
                page_count = len(pdf)
                for number, page in enumerate(pdf, 1):
                    report("Extracting text", number - 1, page_count, f"Reading original page {number}")
                    text = page.get_text("text", sort=True).replace("\x00", "").strip()
                    page_warnings = []
                    method = "native"
                    blocks = [{"text": block[4], "bbox": list(block[:4]), "method": "native"}
                              for block in page.get_text("blocks", sort=True) if block[6] == 0]
                    letters = len(re.sub(r"\s", "", text))
                    image_area = sum(pymupdf.Rect(info["bbox"]).get_area() for info in page.get_image_info())
                    coverage = min(image_area / max(page.rect.get_area(), 1), 1.0)
                    broken_encoding = text.count("\ufffd") > max(2, len(text) * 0.01)
                    suspect = (letters < 30 and (image_area > 0 or len(page.get_drawings()) > 25)) or (coverage > 0.25 and letters < 350) or broken_encoding
                    if suspect:
                        scanned.append(number)
                        if use_ocr is not False:
                            report("Running OCR", number - 1, page_count, f"Recognizing page {number} locally")
                            try:
                                from PIL import Image
                                pix = page.get_pixmap(dpi=180, colorspace=pymupdf.csRGB, alpha=False)
                                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                                ocr_text, ocr_blocks = get_ocr(str(self.settings.data_dir / "ocr_models")).recognize(
                                    image, page.rect.width / pix.width, page.rect.height / pix.height)
                                if len(ocr_text.strip()) >= max(12, letters * 0.8):
                                    text, blocks, method = ocr_text.strip(), ocr_blocks, "rapidocr"
                                    if any(b.get("confidence", 1) < 0.7 for b in blocks):
                                        page_warnings.append(f"Page {number}: some OCR lines have low confidence; verify the original scan.")
                                else:
                                    page_warnings.append(f"Page {number}: automatic OCR found too little readable text.")
                            except Exception:
                                # Only use Tesseract if explicitly already configured.
                                import os
                                from pathlib import Path
                                tessdata = os.getenv("TESSDATA_PREFIX", "")
                                if tessdata and Path(tessdata).is_dir():
                                    try:
                                        tp = page.get_textpage_ocr(language=self.settings.ocr_language, dpi=180, full=True)
                                        text = page.get_text(textpage=tp, sort=True).strip()
                                        blocks = [{"text": b[4], "bbox": list(b[:4]), "method": "tesseract"} for b in page.get_text("blocks", textpage=tp) if b[6] == 0]
                                        method = "tesseract"
                                    except Exception:
                                        page_warnings.append(f"Page {number}: both available OCR paths failed. Retry with a clearer scan.")
                                else:
                                    page_warnings.append(f"Page {number}: local OCR could not run. Retry processing after OCR health recovers.")
                        else:
                            page_warnings.append(f"Page {number} may be scanned; OCR was explicitly disabled by the caller.")
                    # Layout extraction is optional and never allowed to invent
                    # a mandatory OCR dependency. Keep original text for quoting.
                    if method == "native" and len(blocks) >= 8 and letters > 500:
                        try:
                            import pymupdf4llm
                            layout = pymupdf4llm.to_markdown(pdf, pages=[number - 1], show_progress=False, ignore_images=True)
                            if isinstance(layout, str) and len(layout) > len(text) * 0.6:
                                # Store layout alongside native blocks for inspection,
                                # while the citation corpus remains original text.
                                blocks.append({"text": layout, "bbox": None, "method": "layout_markdown", "auxiliary": True})
                        except Exception:
                            pass
                    if broken_encoding and method == "native":
                        text, blocks = "", []
                        page_warnings.append(f"Page {number}: corrupted native text could not be recovered and was excluded.")
                    if not text:
                        page_warnings.append(f"Page {number} contains no extractable text and was not indexed.")
                    warnings.extend(page_warnings)
                    details.append({"page": number, "text": text, "method": method if text else "unreadable",
                                    "quality": "unreadable" if not text else "needs_review" if page_warnings else "usable",
                                    "warnings": page_warnings, "blocks": blocks,
                                    "width": page.rect.width, "height": page.rect.height})
                    for span in tracker.spans(text):
                        section = text[span.start:span.end].strip()
                        locator = display(span.reference) if span.reference else None
                        # Keep a short numbered provision and its list intact.
                        # Long provisions still split within the original page;
                        # their shared locator allows automatic reassembly.
                        intact = span.reference and not span.reference.startswith("paragraph:") and len(section) <= self.settings.chunk_size * 2
                        parts = [section] if intact and section else self.splitter.split_text(section)
                        for part in parts:
                            ordinal = len(chunks)
                            chunk_id = sha256(f"{doc_id}:{number}:{ordinal}:{part}".encode()).hexdigest()
                            chunks.append(Chunk(chunk_id, doc_id, safe_name, number, part, locator, ordinal))
                    report("Extracting text", number, page_count, f"Processed page {number} of {page_count}")
        except LexiRAGError:
            raise
        except Exception as exc:
            raise LexiRAGError("PDF could not be read. It may be damaged or unsupported.") from exc
        if not chunks:
            raise LexiRAGError("No readable text found. Automatic OCR could not recover the pages. Please upload a clearer PDF.")
        report("Splitting into chunks", len(chunks), len(chunks), "Page and clause boundaries preserved")
        return ProcessedPDF(doc_id, safe_name, page_count, chunks, warnings, scanned, details)

