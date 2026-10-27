from hashlib import sha256
import json
import os

from filelock import FileLock

from config.settings import Settings
from core.document_processor import DocumentProcessor
from core.embeddings import LocalEmbeddings
from core.hybrid_retriever import HybridRetriever
from core.models import LexiRAGError
from core.vector_store import VectorStore
from database.store import Database

DOCUMENT_TYPES = ["Judgment", "Act / Statute", "Contract / Agreement", "Case Study", "Other"]


class CorpusService:
    def __init__(self, settings=None, embeddings=None):
        self.settings = settings or Settings()
        self.db = Database(self.settings.data_dir / "metadata.sqlite3")
        self.embeddings = embeddings or LocalEmbeddings(self.settings.embedding_model, str(self.settings.model_cache))
        self.processor = DocumentProcessor(self.settings)
        self.vectors = VectorStore(self.settings.index_dir, self.db, self.settings.embedding_model)
        self.retriever = HybridRetriever(self.db, self.vectors, self.embeddings, self.settings)

    def lock(self):
        return FileLock(str(self.settings.data_dir / "corpus.lock"), timeout=120)

    def upload(self, name, content, document_type="Other", jurisdiction=None, legal_date=None, use_ocr=None, progress=None):
        if document_type not in DOCUMENT_TYPES:
            raise LexiRAGError("Unknown document category.")
        doc_id = sha256(content).hexdigest()
        with self.lock():
            existing = self.db.document(doc_id)
            if existing:
                return {"duplicate": True, "id": doc_id, "warnings": json.loads(existing["warnings"])}
        processed = self.processor.process(name, content, use_ocr, progress=progress)
        # Compute before changing persistent state: failures leave no partial document.
        vector_batches = []
        for offset in range(0, len(processed.chunks), 32):
            if progress:
                progress("Generating embeddings", offset, len(processed.chunks), "Building local search representations")
            vector_batches.append(self.embeddings.embed_documents([c.text for c in processed.chunks[offset:offset + 32]]))
        import numpy as np
        vectors = np.concatenate(vector_batches)
        with self.lock():
            existing = self.db.document(doc_id)
            if existing:
                return {"duplicate": True, "id": doc_id, "warnings": json.loads(existing["warnings"])}
            if any(d["embedding_model"] != self.settings.embedding_model for d in self.db.documents()):
                raise LexiRAGError("Corpus uses another embedding model. Restore the original model or delete/re-upload the corpus.")
            destination = self.settings.upload_dir / f"{doc_id}.pdf"
            temp = destination.with_suffix(".tmp")
            temp.write_bytes(content)
            os.replace(temp, destination)
            try:
                self.db.add(processed, vectors, self.settings.embedding_model, document_type, jurisdiction, legal_date)
                with self.db.connect() as con:
                    con.execute("UPDATE documents SET byte_size=? WHERE id=?", (len(content), doc_id))
            except Exception:
                destination.unlink(missing_ok=True)
                raise
            # Lazy recovery if the process stops between SQLite commit and index write.
            try:
                if progress:
                    progress("Building search index", len(processed.chunks), len(processed.chunks), "Writing the persistent search index")
                self.vectors.rebuild()
            except OSError:
                processed.warnings.append("Document saved. The FAISS index will be rebuilt automatically on the next semantic search.")
        return {"duplicate": False, "id": doc_id, "warnings": processed.warnings, "chunks": len(processed.chunks)}

    def pdf_path(self, doc_id):
        # All paths are server-generated hashes; never join an untrusted filename.
        if len(doc_id) != 64 or any(c not in "0123456789abcdef" for c in doc_id):
            raise LexiRAGError("Invalid document identifier.")
        return self.settings.upload_dir / f"{doc_id}.pdf"

    def delete(self, doc_id):
        with self.lock():
            path = self.pdf_path(doc_id)
            # A file deletion failure leaves the database record available for retry.
            path.unlink(missing_ok=True)
            self.db.delete(doc_id)
            self.vectors.invalidate()
            self.vectors.rebuild()

    def rebuild(self):
        with self.lock():
            self.vectors.rebuild()

    def delete_all(self):
        with self.lock():
            # Also remove orphan PDF/temp artifacts from interrupted ingestion.
            for pattern in ("*.pdf", "*.tmp"):
                for path in self.settings.upload_dir.glob(pattern):
                    path.unlink()
            self.db.clear_corpus()
            self.vectors.invalidate()
            for path in self.settings.results_dir.glob("experiment-*.json"):
                path.unlink()

