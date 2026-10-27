"""Local models are loaded lazily; keyword search never requires a model download."""
from pathlib import Path
from threading import RLock

import numpy as np

from core.models import LexiRAGError


_model_lock = RLock()
_encoders, _rerankers = {}, {}


def _local_snapshot(model_name, cache_folder):
    if Path(model_name).is_dir():
        return model_name
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(model_name, cache_dir=cache_folder, local_files_only=True)
    except Exception:
        return None


def load_encoder(model_name: str, cache_folder: str | None = None):
    from sentence_transformers import SentenceTransformer
    key = model_name, cache_folder
    with _model_lock:
        if key not in _encoders:
            local = _local_snapshot(model_name, cache_folder)
            try:
                model = SentenceTransformer(local or model_name, device="cpu", trust_remote_code=False, cache_folder=cache_folder, local_files_only=bool(local))
            except (OSError, ValueError):
                model = SentenceTransformer(model_name, device="cpu", trust_remote_code=False, cache_folder=cache_folder)
            _encoders[key] = model
        return _encoders[key]


def load_reranker(model_name: str, cache_folder: str | None = None):
    from sentence_transformers import CrossEncoder
    from torch.nn import Identity
    key = model_name, cache_folder
    with _model_lock:
        if key not in _rerankers:
            local = _local_snapshot(model_name, cache_folder)
            try:
                model = CrossEncoder(local or model_name, device="cpu", trust_remote_code=False, cache_folder=cache_folder, local_files_only=bool(local), activation_fn=Identity())
            except (OSError, ValueError):
                model = CrossEncoder(model_name, device="cpu", trust_remote_code=False, cache_folder=cache_folder, activation_fn=Identity())
            _rerankers[key] = model
        return _rerankers[key]


class LocalEmbeddings:
    def __init__(self, model_name: str, cache_folder: str | None = None):
        self.model_name = model_name
        self.cache_folder = cache_folder

    def _encode(self, texts, query=False):
        try:
            model = load_encoder(self.model_name, self.cache_folder)
            method = model.encode_query if query else model.encode_document
            vectors = method(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
            return np.ascontiguousarray(vectors, dtype="float32")
        except Exception as exc:
            raise LexiRAGError("Embedding model could not be loaded or run. Check the model ID, network on first use, and available memory.") from exc

    def embed_documents(self, texts):
        return self._encode(texts)

    def embed_query(self, text):
        return self._encode([text], query=True)[0]

