import json

import pytest

from core.models import LexiRAGError
from evaluation.metrics import mean_measured, precision_at_k, recall_at_k, reciprocal_rank
from evaluation.runner import load_dataset, run_experiment


def test_metric_definitions_and_missing_values():
    assert precision_at_k(["a", "a", "b"], ["a", "c"], 3) == pytest.approx(1 / 3)
    assert recall_at_k(["a", "b"], ["a", "c"], 2) == 0.5
    assert reciprocal_rank(["b", "a"], ["a"]) == 0.5
    assert reciprocal_rank(["b"], ["a"]) == 0.0
    assert recall_at_k(["a"], [], 1) is None
    assert reciprocal_rank(["a"], []) is None
    assert mean_measured([None, float("nan")]) is None
    assert mean_measured([1, None, 0]) == 0.5


def dataset(service):
    relevant = [chunk.id for chunk in service.db.chunks() if "termination" in chunk.text.lower()]
    return "\n".join(json.dumps(row) for row in [
        {"id": "q1", "question": "termination notice", "relevant_chunk_ids": relevant},
        {"id": "u1", "question": "unrelated taxes on Mars", "relevant_chunk_ids": [], "unsupported": True},
    ])


def test_real_experiment_persists_measured_only(populated):
    result = run_experiment(populated, dataset(populated), k=1, modes=["semantic", "hybrid", "keyword"])
    assert len(result["rows"]) == 6
    assert len(result["summary"]) == 3
    assert all(row["precision_at_k"] == 1 for row in result["summary"])
    assert all(row["answer_faithfulness"] is None for row in result["summary"])
    assert all(row["unsupported_rejection_rate"] is None for row in result["summary"])
    assert list(populated.settings.results_dir.glob("experiment-*.json"))
    saved = list(populated.settings.results_dir.glob("experiment-*.json"))[0].read_text()
    assert "unrelated taxes on Mars" not in saved


def test_stale_labels_rejected(populated):
    text = json.dumps({"id": "q1", "question": "privacy", "relevant_chunk_ids": ["does-not-exist"]})
    with pytest.raises(LexiRAGError, match="unknown"):
        load_dataset(text, populated)


@pytest.mark.parametrize("text", ['{}', 'not-json', '{"id":"u1","question":"missing","relevant_chunk_ids":["x"],"unsupported":true}'])
def test_invalid_dataset(service, text):
    with pytest.raises(LexiRAGError, match="Invalid evaluation"):
        load_dataset(text, service)


def test_ragas_requires_answers(populated):
    with pytest.raises(LexiRAGError, match="Enable answer"):
        run_experiment(populated, dataset(populated), ragas=True)

