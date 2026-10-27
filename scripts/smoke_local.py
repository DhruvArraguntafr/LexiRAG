"""Opt-in real model smoke check. Downloads public model weights, uses no LLM key."""
import os
from pathlib import Path
import tempfile

# Keep test downloads inside the workspace by default.
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / "data" / "model_cache"))
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from config.settings import Settings
from core.service import CorpusService
from scripts.create_demo import FIXTURES
import pymupdf


def main():
    settings = Settings()
    with tempfile.TemporaryDirectory(prefix="smoke-", dir=settings.data_dir) as directory:
        from dataclasses import replace
        service = CorpusService(replace(settings, data_dir=Path(directory)))
        for name, pages in FIXTURES.items():
            with pymupdf.open() as pdf:
                for text in pages:
                    page = pdf.new_page()
                    page.insert_textbox(pymupdf.Rect(40, 40, 550, 790), text.replace("—", "-"), fontsize=10)
                content = pdf.tobytes()
            service.upload(name, content, "Contract / Agreement")
        for mode in ("semantic", "keyword", "hybrid"):
            hits = service.retriever.retrieve("What termination notice period is required?", k=3, mode=mode)
            assert hits and any("Clause 3" in (h.chunk.locator or "") for h in hits), f"No relevant notice clause in {mode}"
            print(f"{mode}: {len(hits)} actual passages retrieved", flush=True)
        hits = service.retriever.retrieve("termination notice period", k=3, rerank=True)
        assert hits and "reranker_logit" in hits[0].scores
        print("Real Sentence Transformer, FAISS, BM25, RRF and cross-encoder smoke check passed.", flush=True)


if __name__ == "__main__":
    main()
