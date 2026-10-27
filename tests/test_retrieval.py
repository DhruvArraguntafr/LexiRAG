from dataclasses import replace
import json
from unittest.mock import patch

import numpy as np
import pytest

from core.hybrid_retriever import reciprocal_rank_fusion
from core.models import LexiRAGError, SearchFilters
from core.service import CorpusService
from tests.conftest import TestEmbeddings, make_pdf


@pytest.mark.parametrize("mode", ["semantic", "keyword", "hybrid"])
def test_genuine_retrieval(populated, mode):
    hits = populated.retriever.retrieve("termination notice", k=2, mode=mode)
    assert hits[0].chunk.document_name == "Agreement.pdf"
    assert hits[0].chunk.page == 1
    assert "notice" in hits[0].chunk.text.lower()
    assert hits[0].scores


def test_rrf_agreement_and_deduplication():
    fused = reciprocal_rank_fusion([[('a', 0.8), ('b', 0.7)], [('b', 5), ('c', 4)]])
    assert fused[0][0] == 'b'
    assert len({item[0] for item in fused}) == 3


def test_filters_applied_before_semantic_top_k(populated):
    doc = next(d for d in populated.db.documents() if d["name"] == "Privacy.pdf")
    hits = populated.retriever.retrieve("termination notice", k=1, filters=SearchFilters(document_ids=(doc["id"],)))
    assert len(hits) == 1 and hits[0].chunk.document_id == doc["id"]
    assert not populated.retriever.retrieve("privacy", filters=SearchFilters(jurisdiction="Unknown"))
    assert all(hit.chunk.document_name == "Privacy.pdf" for hit in populated.retriever.retrieve("privacy", filters=SearchFilters(document_type="Act / Statute", date_from="2024-01-01")))


def test_duplicates_preserve_index_and_delete_excludes_results(populated):
    original = populated.db.documents()[0]
    content = populated.pdf_path(original["id"]).read_bytes()
    revision = populated.db.revision()
    assert populated.upload("renamed.pdf", content)["duplicate"]
    assert populated.db.revision() == revision
    populated.delete(original["id"])
    assert not populated.pdf_path(original["id"]).exists()
    for mode in ("semantic", "keyword", "hybrid"):
        assert all(hit.chunk.document_id != original["id"] for hit in populated.retriever.retrieve("privacy notice", mode=mode))
    _, ids = populated.vectors.load()
    assert set(ids) == {c.id for c in populated.db.chunks()}


def test_restart_and_corrupt_index_recovery(populated):
    initial = [hit.chunk.id for hit in populated.retriever.retrieve("privacy consent")]
    populated.vectors.path.write_bytes(b"corrupted")
    restarted = CorpusService(populated.settings, TestEmbeddings())
    assert [hit.chunk.id for hit in restarted.retriever.retrieve("privacy consent")] == initial
    restarted.vectors.manifest.write_text("broken json")
    assert restarted.retriever.retrieve("privacy consent")
    manifest = json.loads(restarted.vectors.manifest.read_text())
    assert manifest["revision"] == restarted.db.revision()


def test_rollback_on_embedding_failure(service):
    with patch.object(service.embeddings, "embed_documents", side_effect=LexiRAGError("offline")):
        with pytest.raises(LexiRAGError):
            service.upload("failed.pdf", make_pdf(["Privacy and consent obligations in this legal teaching fixture."]))
    assert service.db.documents() == []
    assert not list(service.settings.upload_dir.glob("*.pdf"))


def test_invalid_date_rolls_back_pdf(service):
    with pytest.raises(LexiRAGError, match="Legal date"):
        service.upload("failed.pdf", make_pdf(["A legal document discusses privacy safeguards and consent."]), legal_date="yesterday")
    assert service.db.documents() == []
    assert not list(service.settings.upload_dir.glob("*.pdf"))


def test_model_mismatch_detected(populated):
    other = CorpusService(replace(populated.settings, embedding_model="different"), TestEmbeddings())
    with pytest.raises(LexiRAGError, match="differs"):
        other.retriever.retrieve("privacy")
    assert other.retriever.retrieve("privacy", mode="keyword")


def test_keyword_does_not_load_embedding_model(populated):
    with patch.object(populated.embeddings, "embed_query", side_effect=AssertionError("must stay local/no model")):
        assert populated.retriever.retrieve("privacy", mode="keyword")
    assert not populated.retriever.retrieve("zzzxunknownterm", mode="keyword")


def test_reranker_scores_and_failure(populated):
    class Reranker:
        def predict(self, pairs, **kwargs):
            return np.arange(len(pairs), dtype="float32")
    with patch("core.hybrid_retriever.load_reranker", return_value=Reranker()):
        hits = populated.retriever.retrieve("privacy notice", rerank=True)
        scores = [hit.scores["reranker_logit"] for hit in hits]
        assert scores == sorted(scores, reverse=True)
    with patch("core.hybrid_retriever.load_reranker", side_effect=RuntimeError("offline")):
        with pytest.raises(LexiRAGError, match="Reranker"):
            populated.retriever.retrieve("privacy", rerank=True)


@pytest.mark.parametrize("kwargs", [{"question": ""}, {"question": "x" * 6001}, {"question": "privacy", "k": 0}, {"question": "privacy", "mode": "invalid"}, {"question": "privacy", "filters": SearchFilters(date_from="2025-01-01", date_to="2020-01-01")}])
def test_retrieval_input_errors(service, kwargs):
    with pytest.raises(LexiRAGError):
        service.retriever.retrieve(**kwargs)


def test_invalid_path_identifier(service):
    with pytest.raises(LexiRAGError):
        service.pdf_path("../private")


def test_bulk_deletion_clears_sources_indexes_and_analytics(populated):
    populated.db.record_activity("research", 0.1, "hybrid")
    (populated.settings.upload_dir / "orphan.pdf").write_bytes(b"interrupted ingestion")
    (populated.settings.results_dir / "experiment-test.json").write_text("{}")
    populated.delete_all()
    assert populated.db.documents() == []
    assert populated.db.chunks() == []
    assert populated.db.analytics()["queries"] == 0
    assert not populated.vectors.path.exists()
    assert not list(populated.settings.upload_dir.iterdir())
    assert not list(populated.settings.results_dir.iterdir())
