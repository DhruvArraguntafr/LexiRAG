"""Genuine raster-only and mixed PDFs for offline OCR validation."""
from pathlib import Path
import pymupdf

PAGES = [
    "SYNTHETIC OCR TEACHING AGREEMENT\n\nClause 7 Termination notice\nEither party may terminate this agreement by giving thirty days written notice.\nFees for completed services remain payable.\n\nThis teaching agreement is dated 15 January 2025.",
    "SYNTHETIC OCR TEACHING AGREEMENT\n\nClause 8 Data retention\nPersonal data must be deleted within sixty days after termination.\nThe provider must protect customer records with access controls.\n\nThe fictional service period ends on 31 January 2026.",
]


def create_fixtures(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    images = []
    with pymupdf.open() as native:
        for text in PAGES:
            page = native.new_page()
            assert page.insert_textbox(pymupdf.Rect(45, 60, 550, 780), text, fontsize=14) >= 0
            images.append(page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).tobytes("png"))
        native.save(directory / "Native-Teaching.pdf")
    with pymupdf.open() as scanned:
        for image in images:
            page = scanned.new_page()
            page.insert_image(page.rect, stream=image)
        scanned.save(directory / "Scanned-Teaching.pdf")
    with pymupdf.open() as mixed, pymupdf.open(directory / "Native-Teaching.pdf") as native:
        mixed.insert_pdf(native, from_page=0, to_page=0)
        page = mixed.new_page()
        page.insert_image(page.rect, stream=images[1])
        mixed.save(directory / "Mixed-Teaching.pdf")
    with pymupdf.open() as incomplete:
        page = incomplete.new_page()
        page.insert_image(page.rect, stream=images[0])
        page.insert_text((45, 30), "A native header with a scanned body", fontsize=10)
        incomplete.save(directory / "Incomplete-Text.pdf")
    return {name: directory / name for name in ["Native-Teaching.pdf", "Scanned-Teaching.pdf", "Mixed-Teaching.pdf", "Incomplete-Text.pdf"]}


if __name__ == "__main__":
    create_fixtures("data/ocr-validation/fixtures")
    print("Generated native, scanned, mixed and incomplete-text PDF fixtures.")
