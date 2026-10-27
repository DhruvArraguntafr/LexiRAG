import numpy as np

from core.models import LexiRAGError
from core.service import DOCUMENT_TYPES


class DocumentService:
    def __init__(self, corpus, workspaces):
        self.corpus, self.workspaces, self.db = corpus, workspaces, corpus.db

    def update(self, document_id, name, category, jurisdiction=None, legal_date=None):
        if not self.db.document(document_id) or not name.strip() or len(name) > 240:
            raise LexiRAGError("Use a document title of 1–240 characters.")
        if category not in DOCUMENT_TYPES:
            raise LexiRAGError("Choose a document category.")
        if legal_date:
            from datetime import date
            try:
                date.fromisoformat(legal_date)
            except ValueError as exc:
                raise LexiRAGError("Legal dates must be verified YYYY-MM-DD dates.") from exc
        with self.db.connect() as con:
            con.execute("UPDATE documents SET name=?,document_type=?,jurisdiction=?,legal_date=? WHERE id=?",
                        (name.strip(), category, jurisdiction or None, legal_date or None, document_id))
            con.execute("UPDATE chunks SET document_name=? WHERE document_id=?", (name.strip(), document_id))

    def reindex(self, document_id, progress=None):
        doc = self.db.document(document_id)
        if not doc:
            raise LexiRAGError("Document not found.")
        content = self.corpus.pdf_path(document_id).read_bytes()
        processed = self.corpus.processor.process(doc["name"] if doc["name"].lower().endswith(".pdf") else doc["name"] + ".pdf", content, progress=progress)
        batches = []
        for offset in range(0, len(processed.chunks), 32):
            if progress:
                progress("Generating embeddings", offset, len(processed.chunks), "Reindexing source text")
            batches.append(self.corpus.embeddings.embed_documents([c.text for c in processed.chunks[offset:offset + 32]]))
        # Nothing is removed until replacement extraction and embeddings succeed.
        with self.corpus.lock():
            self.db.add(processed, np.concatenate(batches), self.corpus.settings.embedding_model, doc["document_type"], doc["jurisdiction"], doc["legal_date"])
            self.corpus.vectors.rebuild()
        return {"id": document_id, "warnings": processed.warnings, "chunks": len(processed.chunks)}
