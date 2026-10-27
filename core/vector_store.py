"""Persistent FAISS cosine index. SQLite vectors allow safe, offline recovery.

The caller holds the corpus FileLock for every read/mutation. Never deserialize
pickle; the manifest checksum is checked before FAISS reads an index file.
"""
from hashlib import sha256
import json
import os

import faiss
import numpy as np

from core.models import LexiRAGError


class VectorStore:
    def __init__(self, directory, database, model_name):
        self.directory, self.db, self.model_name = directory, database, model_name
        self.path = directory / "index.faiss"
        self.manifest = directory / "manifest.json"

    def invalidate(self):
        self.manifest.unlink(missing_ok=True)
        self.path.unlink(missing_ok=True)

    def rebuild(self):
        chunks, matrix = self.db.chunks(with_vectors=True)
        if not chunks:
            self.invalidate()
            return None, []
        models = {doc["embedding_model"] for doc in self.db.documents()}
        if models != {self.model_name}:
            raise LexiRAGError("The configured embedding model differs from the indexed model. Restore EMBEDDING_MODEL or re-upload the corpus.")
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(np.ascontiguousarray(matrix, dtype="float32"))
        temp_index = self.path.with_suffix(".tmp")
        temp_manifest = self.manifest.with_suffix(".tmp")
        faiss.write_index(index, str(temp_index))
        manifest = {"revision": self.db.revision(), "model": self.model_name,
                    "ids": [c.id for c in chunks], "dimension": matrix.shape[1],
                    "checksum": sha256(temp_index.read_bytes()).hexdigest()}
        temp_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        os.replace(temp_index, self.path)
        os.replace(temp_manifest, self.manifest)
        return index, manifest["ids"]

    def load(self):
        if not self.db.documents():
            self.invalidate()
            return None, []
        try:
            info = json.loads(self.manifest.read_text(encoding="utf-8"))
            if info["revision"] != self.db.revision() or info["model"] != self.model_name:
                return self.rebuild()
            if sha256(self.path.read_bytes()).hexdigest() != info["checksum"]:
                return self.rebuild()
            index = faiss.read_index(str(self.path))
            if index.ntotal != len(info["ids"]) or index.d != info["dimension"]:
                return self.rebuild()
            return index, info["ids"]
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            return self.rebuild()

    def search(self, query_vector, chunks, k):
        if not chunks:
            return []
        index, ids = self.load()
        allowed = {c.id for c in chunks}
        if allowed != set(ids):
            # Filter BEFORE nearest-neighbour search, preventing post-filter starvation.
            corpus, matrix = self.db.chunks(with_vectors=True)
            selected = [(c.id, v) for c, v in zip(corpus, matrix) if c.id in allowed]
            ids = [i for i, _ in selected]
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(np.ascontiguousarray([v for _, v in selected], dtype="float32"))
        query = np.ascontiguousarray([query_vector], dtype="float32")
        if query.shape[1] != index.d or not np.isfinite(query).all():
            raise LexiRAGError("Query embedding is incompatible with this index; check EMBEDDING_MODEL.")
        norm = np.linalg.norm(query)
        if norm == 0:
            raise LexiRAGError("Query embedding is empty.")
        scores, positions = index.search(query / norm, min(k, index.ntotal))
        return [(ids[int(pos)], float(score)) for score, pos in zip(scores[0], positions[0]) if pos >= 0]

