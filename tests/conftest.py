import re

import numpy as np
import pymupdf
import pytest

from config.settings import Settings
from core.models import EvidenceRef, Finding, GroundedAnswer
from core.service import CorpusService


@pytest.fixture(autouse=True)
def offline_comparison_default(monkeypatch):
    """Unit tests use explicit reranker doubles, never download real weights."""
    monkeypatch.setattr("core.comparison_retriever.AUTO_RERANK", False)


class TestEmbeddings:
    """Deterministic offline test double; never used in the application."""
    model_name = "test-only"
    vocabulary = ["privacy", "consent", "termination", "notice", "days", "payment", "tax", "court", "contract", "data"]

    def embed_documents(self, texts):
        matrix = []
        for text in texts:
            terms = re.findall(r"\w+", text.lower())
            vector = np.array([terms.count(term) for term in self.vocabulary] + [0.1], dtype="float32")
            matrix.append(vector / np.linalg.norm(vector))
        return np.stack(matrix)

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class ExtractiveTestGenerator:
    """Uses exact supplied text so no test needs Gemini/network access."""
    def __init__(self):
        self.calls = []

    def generate(self, question, sources, instruction=""):
        self.calls.append((question, sources, instruction))
        findings = []
        for sid, hit in list(sources.items())[:2]:
            quote = hit.chunk.text[:100]
            findings.append(Finding(heading="Supported finding", statement="The supplied document addresses this issue.", kind="fact", evidence=[EvidenceRef(source_id=sid, quote=quote)]))
        return GroundedAnswer(insufficient_evidence=False, findings=findings, limitations=[])


def make_pdf(pages):
    with pymupdf.open() as pdf:
        for text in pages:
            page = pdf.new_page()
            page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=10)
        return pdf.tobytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "corpus", embedding_model="test-only", api_key="", chunk_size=400, chunk_overlap=60, context_chars=2400)


@pytest.fixture
def service(settings):
    return CorpusService(settings, TestEmbeddings())


@pytest.fixture
def populated(service):
    service.upload("Privacy.pdf", make_pdf([
        "Section 1 Privacy and consent\nThe data controller requires informed consent before using personal data. Privacy safeguards apply to the contract.",
        "Section 2 Data safeguards\nThe parties protect personal data with access controls. Privacy records must be retained securely.",
    ]), "Act / Statute", "India", "2024-01-02")
    service.upload("Agreement.pdf", make_pdf([
        "Clause 3 Termination notice\nEither party may terminate the contract by giving thirty days written notice. Payment remains due for completed services.",
    ]), "Contract / Agreement", "Delhi", "2023-05-06")
    return service

