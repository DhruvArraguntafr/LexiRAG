"""Generate openly synthetic contract fixtures, never presented as legal authority."""
import argparse
import json

import pymupdf

from config.settings import Settings
from core.models import LexiRAGError
from core.service import CorpusService

FIXTURES = {
    "Teaching-Agreement-A.pdf": [
        "SYNTHETIC TEACHING AGREEMENT A — NOT A REAL LEGAL INSTRUMENT\n\n"
        "Clause 1 Privacy and consent\nThe service provider shall collect personal data only after obtaining informed written consent from the customer. The customer may withdraw consent at any time by written notice.\n\n"
        "Clause 2 Security and retention\nThe provider shall restrict access to personal data to authorized employees. Personal data shall be deleted within thirty days after termination, unless the parties agree in writing to a different period.",
        "SYNTHETIC TEACHING AGREEMENT A — FOR SOFTWARE TESTING ONLY\n\n"
        "Clause 3 Termination and notice\nEither party may terminate this agreement by giving thirty days written notice. Fees for services already completed remain payable.\n\n"
        "Clause 4 Important dates\nThis teaching agreement is dated 15 January 2025. The fictional service period begins on 1 February 2025 and ends on 31 January 2026.",
    ],
    "Teaching-Agreement-B.pdf": [
        "SYNTHETIC TEACHING AGREEMENT B — NOT A REAL LEGAL INSTRUMENT\n\n"
        "Clause 1 Privacy and consent\nThe service provider shall obtain informed written consent before processing customer personal data. Withdrawal of consent must be submitted through the designated contact address.\n\n"
        "Clause 2 Security and retention\nThe provider shall encrypt stored customer data and restrict access to authorized staff. Personal data shall be deleted within sixty days after termination.",
        "SYNTHETIC TEACHING AGREEMENT B — FOR SOFTWARE TESTING ONLY\n\n"
        "Clause 3 Termination and notice\nEither party may terminate this agreement by giving sixty days written notice. Undisputed fees for completed services remain due.\n\n"
        "Clause 4 Important dates\nThis teaching agreement is dated 20 January 2025. The fictional service period begins on 1 March 2025 and ends on 28 February 2026.",
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", action="store_true", help="Index generated PDFs with the real local embedding model and export fixture relevance labels")
    args = parser.parse_args()
    settings = Settings()
    directory = settings.data_dir / "demo"
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for name, pages in FIXTURES.items():
        destination = directory / name
        if not destination.exists():
            with pymupdf.open() as pdf:
                for text in pages:
                    page = pdf.new_page()
                    page.insert_textbox(pymupdf.Rect(45, 45, 550, 790), text.replace("—", "-"), fontsize=11)
                pdf.save(destination)
        files.append(destination)
    print(f"Created synthetic teaching PDFs in {directory}. These are not real law or real contracts.")
    if args.index:
        service = CorpusService(settings)
        ids = []
        for path in files:
            ids.append(service.upload(path.name, path.read_bytes(), "Contract / Agreement", jurisdiction="Synthetic teaching fixture")["id"])
        chunks = service.db.chunks()
        labels = []
        for index, doc_id in enumerate(ids):
            relevant = [c.id for c in chunks if c.document_id == doc_id and c.locator and c.locator.startswith("Clause 3")]
            labels.append({"id": f"fixture-notice-{index + 1}", "question": "What termination notice period does this teaching agreement require?",
                           "relevant_chunk_ids": relevant, "document_ids": [doc_id], "unsupported": False})
        labels.append({"id": "fixture-unsupported", "question": "Which Supreme Court judgment overrides these teaching agreements?",
                       "relevant_chunk_ids": [], "document_ids": ids, "unsupported": True})
        dataset = directory / "fixture-questions.jsonl"
        dataset.write_text("\n".join(json.dumps(row) for row in labels), encoding="utf-8")
        print(f"Indexed real embeddings and wrote {dataset}. Labels describe synthetic fixture clauses only; do not treat results as a legal benchmark.")


if __name__ == "__main__":
    try:
        main()
    except LexiRAGError as exc:
        raise SystemExit(str(exc)) from None

