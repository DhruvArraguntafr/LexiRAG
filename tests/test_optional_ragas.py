"""Exercise real Ragas/Instructor code with mocked Gemini-compatible HTTP only."""
from dataclasses import replace
import json

import pytest

from core.rag_pipeline import RAGPipeline
from tests.conftest import ExtractiveTestGenerator


def test_ragas_real_collections_and_async_adapter(populated):
    pytest.importorskip("ragas")
    import httpx
    from openai import AsyncOpenAI
    from evaluation.answer_quality import AnswerQuality

    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if "StatementGeneratorOutput" in json.dumps(body["messages"]):
            output = {"statements": ["The document addresses the research issue."]}
        else:
            output = {"statements": [{"statement": "The document addresses the research issue.", "reason": "Mocked external judge for integration test only.", "verdict": 1}]}
        return httpx.Response(200, json={"id": "test-response", "object": "chat.completion", "created": 1,
                              "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(output)}}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    def client_factory(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    judge = AnswerQuality(replace(populated.settings, api_key="test-key-not-real"))
    judge.client_factory = client_factory
    result = RAGPipeline(populated, ExtractiveTestGenerator()).ask("privacy")
    # Two sequential calls prove that event-loop/client lifecycle is correct.
    for _ in range(2):
        scores = judge.score(result)
        assert scores == {"answer_faithfulness": 1.0, "citation_correctness": 1.0}
    assert requests and all(body["model"] == populated.settings.gemini_model for body in requests)

