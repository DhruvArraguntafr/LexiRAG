from functools import lru_cache
import json

import pymupdf

from core.models import LexiRAGError
from core.citation_manager import normalize, match_quote


class SourceService:
    def __init__(self, corpus):
        self.corpus, self.db = corpus, corpus.db

    def locations(self, doc_id, page_number, quote):
        record = self.db.document(doc_id)
        if not record or not 1 <= page_number <= record["pages"]:
            raise LexiRAGError("Original source page is unavailable.")
        with pymupdf.open(self.corpus.pdf_path(doc_id)) as pdf:
            page = pdf[page_number - 1]
            if quote:
                rects = page.search_for(normalize(quote))
                if rects:
                    return [list(rect) for rect in rects], "Matching native PDF text"
        detail = self.db.page(doc_id, page_number)
        if quote and detail:
            blocks = [b for b in json.loads(detail["blocks"]) if b.get("bbox") and not b.get("auxiliary")]
            combined, intervals = "", []
            for block in blocks:
                text = normalize(block["text"])
                start = len(combined)
                combined += text + " "
                intervals.append((start, len(combined), block["bbox"]))
            match = match_quote(quote, combined)
            if match:
                selected = [box for left, right, box in intervals if right > match.start and left < match.end]
                return selected, "OCR line regions — verify the original image" if detail["method"] == "rapidocr" else "Extracted text regions"
        return [], "Exact highlighting unavailable; inspect the original page and quotation"

    def render(self, doc_id, page_number, quote="", scale=1.5):
        doc = self.db.document(doc_id)
        if not doc:
            raise LexiRAGError("Document was deleted.")
        if not 1 <= page_number <= doc["pages"] or not 0.5 <= scale <= 2.5:
            raise LexiRAGError("Invalid source page or zoom.")
        rects, label = self.locations(doc_id, page_number, quote)
        return self._render(doc_id, page_number, quote, scale, self.db.revision(), json.dumps(rects)), label

    @lru_cache(maxsize=32)
    def _render(self, doc_id, page_number, quote, scale, revision, rectangles):
        with pymupdf.open(self.corpus.pdf_path(doc_id)) as pdf:
            page = pdf[page_number - 1]
            for rectangle in json.loads(rectangles):
                annotation = page.add_rect_annot(pymupdf.Rect(rectangle))
                annotation.set_colors(stroke=(0.06, 0.7, 0.65), fill=(0.35, 0.9, 0.8))
                annotation.set_opacity(0.25)
                annotation.update()
            return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
