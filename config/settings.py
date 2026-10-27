from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LEXIRAG_DATA_DIR", str(ROOT / "data"))).resolve())
    embedding_model: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    reranker_model: str = field(default_factory=lambda: os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L6-v2"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""), repr=False)
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "30")))
    max_pdf_pages: int = field(default_factory=lambda: int(os.getenv("MAX_PDF_PAGES", "1000")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "900")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "120")))
    context_chars: int = field(default_factory=lambda: int(os.getenv("LLM_CONTEXT_CHARS", "24000")))
    ocr_language: str = field(default_factory=lambda: os.getenv("OCR_LANGUAGE", "eng"))

    def __post_init__(self):
        if not 100 <= self.chunk_size <= 1600 or not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("Use CHUNK_SIZE 100–1600 and CHUNK_OVERLAP smaller than CHUNK_SIZE.")
        if self.context_chars < self.chunk_size * 2 or self.max_upload_mb < 1 or self.max_pdf_pages < 1:
            raise ValueError("Invalid context or upload limits in configuration.")
        for directory in (self.data_dir, self.upload_dir, self.index_dir, self.results_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def upload_dir(self):
        return self.data_dir / "uploads"

    @property
    def index_dir(self):
        return self.data_dir / "vector_store"

    @property
    def results_dir(self):
        return self.data_dir / "evaluation"

    @property
    def model_cache(self):
        return Path(os.getenv("HF_HOME", str(self.data_dir / "model_cache"))) / "hub"

