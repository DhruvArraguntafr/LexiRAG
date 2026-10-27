"""Private rotating diagnostics: question, filters and IDs, never source text."""
from dataclasses import asdict
import json
import logging
from logging.handlers import RotatingFileHandler
from core.legal_sections import references

LOGGER = logging.getLogger("lexirag.retrieval")


def configure(directory):
    directory = directory / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "retrieval.jsonl"
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(path.resolve()) for h in LOGGER.handlers):
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def record(question, filters, phase, hits, **extra):
    LOGGER.info(json.dumps({"question": question, "filters": asdict(filters) if filters else {}, "phase": phase,
                           "chunks": [{"id": h.chunk.id, "document_id": h.chunk.document_id,
                                       "page": h.chunk.page, "sections": references(h.chunk.locator or ""),
                                       "scores": h.scores} for h in hits], **extra}, ensure_ascii=True))
