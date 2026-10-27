"""Recover page records for older indexed PDFs without replacing saved chunks."""
import json
import logging
import re

import pymupdf


def restore_page_records(database, document_id):
    if not re.fullmatch(r"[0-9a-f]{64}", document_id):
        return
    path = database.path.parent / "uploads" / (document_id + ".pdf")
    if not path.is_file():
        return
    with database.connect() as con:
        present = {r[0] for r in con.execute("SELECT page FROM document_pages WHERE document_id=?", (document_id,))}
    records = []
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                return
            for number, page in enumerate(pdf, 1):
                if number in present:
                    continue
                text = page.get_text("text", sort=True).replace("\x00", "").strip()
                method, blocks = "native", []
                blocks = [{"text": b[4], "bbox": list(b[:4]), "method": method}
                          for b in page.get_text("blocks", sort=True) if b[6] == 0]
                if not text and page.get_images():
                    try:
                        from PIL import Image
                        from core.ocr_engine import get_ocr
                        pix = page.get_pixmap(dpi=180, colorspace=pymupdf.csRGB, alpha=False)
                        text, blocks = get_ocr(str(database.path.parent / "ocr_models")).recognize(
                            Image.frombytes("RGB", (pix.width, pix.height), pix.samples),
                            page.rect.width / pix.width, page.rect.height / pix.height)
                        method = "rapidocr"
                    except Exception:
                        method = "unreadable"
                records.append((document_id, number, text, method, "usable" if text else "unreadable",
                                "[]", json.dumps(blocks), page.rect.width, page.rect.height))
    except (OSError, RuntimeError, ValueError):
        logging.getLogger("lexirag.retrieval").warning(json.dumps({"phase": "legacy_page_recovery_failed", "document_id": document_id}))
        return
    if records:
        with database.connect() as con:
            con.executemany("INSERT OR IGNORE INTO document_pages VALUES(?,?,?,?,?,?,?,?,?)", records)
        logging.getLogger("lexirag.retrieval").info(json.dumps({"phase": "legacy_pages_restored", "document_id": document_id, "pages": len(records)}))
