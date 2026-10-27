"""Optional Ragas collections API; no legacy LangchainLLMWrapper/evaluate API."""
import os
import asyncio

from core.models import LexiRAGError


class AnswerQuality:
    def __init__(self, settings):
        if not settings.api_key:
            raise LexiRAGError("GOOGLE_API_KEY is required for Ragas answer evaluation.")
        # Ragas telemetry contains usage data. Keep it disabled for local research.
        os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
        try:
            from openai import AsyncOpenAI
            from ragas.llms import llm_factory
            from ragas.metrics.collections import Faithfulness
            # Google's documented OpenAI-compatible Gemini endpoint avoids
            # Instructor's Google SDK safety-settings compatibility problem.
            self.settings = settings
            self.client_factory = AsyncOpenAI
            self.llm_factory = llm_factory
            self.metric_type = Faithfulness
        except ImportError as exc:
            raise LexiRAGError("Install requirements-eval.txt to run Ragas evaluation.") from exc
        except Exception as exc:
            raise LexiRAGError("Ragas Gemini evaluator could not be initialized. Verify optional dependency versions and Gemini configuration.") from exc

    def score(self, result):
        if not result.answer.findings:
            return {"answer_faithfulness": None, "citation_correctness": None}
        try:
            return asyncio.run(self._score(result))
        except Exception as exc:
            raise LexiRAGError("Ragas scoring failed. Check evaluator model access, quota and dependency compatibility.") from exc

    async def _score(self, result):
        from evaluation.metrics import mean_measured
        # Collections metrics call agenerate(), even from their sync wrappers.
        # A per-evaluation async client also prevents closed-loop HTTP reuse
        # when Streamlit/CLI score multiple questions sequentially.
        async with self.client_factory(api_key=self.settings.api_key,
                                       base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                                       timeout=90, max_retries=2) as client:
            llm = self.llm_factory(self.settings.gemini_model, provider="openai", client=client,
                                   adapter="instructor", temperature=1.0, max_tokens=8192)
            scorer = self.metric_type(llm=llm)
            response = "\n".join(f.statement for f in result.answer.findings)
            faith = await scorer.ascore(user_input=result.question, response=response,
                                        retrieved_contexts=[h.chunk.text for h in result.sources.values()])
            citations = []
            for finding in result.answer.findings:
                for ref in finding.evidence:
                    score = await scorer.ascore(user_input=result.question, response=finding.statement,
                                                retrieved_contexts=[result.sources[ref.source_id].chunk.text])
                    citations.append(score.value)
            return {"answer_faithfulness": mean_measured([faith.value]), "citation_correctness": mean_measured(citations)}

