from dataclasses import replace
from unittest.mock import patch

from langchain_core.runnables import RunnableLambda
import pymupdf
import pytest

from core.citation_manager import validate_answer, verify_ref
from core.document_comparison import DocumentComparator
from core.models import EvidenceRef, Finding, GroundedAnswer, LexiRAGError
from core.rag_pipeline import GeminiGenerator, RAGPipeline, SYSTEM_PROMPT
from core.summarizer import DocumentSummarizer
from tests.conftest import ExtractiveTestGenerator, make_pdf
from utils.reports import report_pdf


def test_grounded_answer_with_real_retrieved_sources(populated):
    generator = ExtractiveTestGenerator()
    result = RAGPipeline(populated, generator).ask("termination notice", k=2)
    assert result.answer.findings
    assert result.latency_seconds > 0
    assert result.citation_valid == result.citation_attempts > 0
    assert all(verify_ref(ref, result.sources) for finding in result.answer.findings for ref in finding.evidence)
    assert populated.db.analytics()["queries"] == 1


@pytest.mark.parametrize("bad", ["unknown_id", "fabricated_quote", "inline_marker"])
def test_fabricated_citations_fail_closed(populated, bad):
    pipeline = RAGPipeline(populated, ExtractiveTestGenerator())
    sources = pipeline.select_sources(populated.retriever.retrieve("privacy"))
    sid, hit = next(iter(sources.items()))
    ref = EvidenceRef(source_id="S999" if bad == "unknown_id" else sid, quote="The court invented an unrelated legal principle." if bad == "fabricated_quote" else hit.chunk.text[:70])
    finding = Finding(heading="Finding", statement="Claim [S1]" if bad == "inline_marker" else "Claim", kind="fact", evidence=[ref])
    result, _, _ = validate_answer(GroundedAnswer(insufficient_evidence=False, findings=[finding], limitations=[]), sources)
    assert not result.findings
    assert result.insufficient_evidence
    assert "withheld" in " ".join(result.limitations)


def test_no_evidence_means_no_external_call(service):
    generator = ExtractiveTestGenerator()
    result = RAGPipeline(service, generator).ask("An unsupported question?", mode="keyword")
    assert result.answer.insufficient_evidence
    assert not generator.calls
    assert not result.sources


def test_missing_key_gives_actionable_error(settings, populated):
    sources = RAGPipeline(populated).select_sources(populated.retriever.retrieve("privacy"))
    with pytest.raises(LexiRAGError, match="GOOGLE_API_KEY"):
        GeminiGenerator(settings).generate("privacy", sources)


def test_langchain_gemini_structured_api_and_untrusted_evidence(settings, populated):
    generator = ExtractiveTestGenerator()
    sources = RAGPipeline(populated).select_sources(populated.retriever.retrieve("privacy"))
    expected = generator.generate("privacy", sources)
    runnable = RunnableLambda(lambda prompt: expected)
    with patch("langchain_google_genai.ChatGoogleGenerativeAI") as model:
        model.return_value.with_structured_output.return_value = runnable
        response = GeminiGenerator(replace(settings, api_key="test-key-not-real")).generate("privacy", sources)
        assert response == expected
        assert model.call_args.kwargs["vertexai"] is False
        assert model.return_value.with_structured_output.call_args.kwargs["method"] == "json_schema"
    assert "untrusted DATA" in SYSTEM_PROMPT


def test_external_errors_do_not_expose_provider_prompt(settings, populated):
    sources = RAGPipeline(populated).select_sources(populated.retriever.retrieve("privacy"))
    with patch("langchain_google_genai.ChatGoogleGenerativeAI", side_effect=RuntimeError("SECRET CONFIDENTIAL CONTENT")):
        with pytest.raises(LexiRAGError) as caught:
            GeminiGenerator(replace(settings, api_key="test")).generate("question", sources)
    assert "SECRET" not in str(caught.value)


def test_comparison_retrieves_each_document(populated):
    ids = [doc["id"] for doc in populated.db.documents()]
    generator = ExtractiveTestGenerator()
    result = DocumentComparator(populated, generator).compare(ids, "Compare privacy and termination notice", k=1)
    assert {hit.chunk.document_id for hit in result.sources.values()} == set(ids)
    assert len(result.comparison_rows) == 2
    assert any("Agreement.pdf" in key for key in result.comparison_rows[0])


def test_comparison_requires_multiple_documents(populated):
    with pytest.raises(LexiRAGError, match="two"):
        DocumentComparator(populated).compare([populated.db.documents()[0]["id"]], "compare")


def test_hierarchical_summary_covers_all_first_stage_chunks(service):
    content = make_pdf([f"Section {i} Privacy obligations\n" + (f"Privacy consent duty for party {i}. " * 45) for i in range(1, 13)])
    doc_id = service.upload("long.pdf", content)["id"]
    generator = ExtractiveTestGenerator()
    result = DocumentSummarizer(service, generator).summarize(doc_id)
    first_chunk_ids = {c.id for c in service.db.chunks()}
    seen = {hit.chunk.id for _, sources, _ in generator.calls for hit in sources.values()}
    assert first_chunk_ids <= seen
    assert len(generator.calls) > 2
    assert result.answer.findings
    assert all(verify_ref(ref, result.sources) for f in result.answer.findings for ref in f.evidence)
    assert any("summary stage" in text for text in result.answer.limitations)


def test_summary_rejects_missing_document(service):
    with pytest.raises(LexiRAGError, match="no indexed"):
        DocumentSummarizer(service).summarize("missing")


def test_pdf_report_is_readable_and_contains_citations(populated):
    result = RAGPipeline(populated, ExtractiveTestGenerator()).ask("termination notice")
    pdf_bytes = report_pdf(result)
    assert pdf_bytes.startswith(b"%PDF-")
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        text = " ".join(page.get_text() for page in pdf)
    assert "Agreement.pdf" in text
    assert "PDF page 1" in text
    assert "termination notice" in text
    assert "Limitations" in text


def test_comparison_report_formats_markdown_labels_and_quotes(populated):
    ids = [doc["id"] for doc in populated.db.documents()]
    result = DocumentComparator(populated, ExtractiveTestGenerator()).compare(ids, "Compare privacy and notice", k=1)
    with pymupdf.open(stream=report_pdf(result), filetype="pdf") as pdf:
        text = "\n".join(page.get_text() for page in pdf)
        assert "Issue:" in text and "**Issue:**" not in text
        assert not any(line.startswith("> ") for line in text.splitlines())
        for page in pdf:
            page_text = page.get_text()
            if "Supporting evidence and citations" in page_text:
                following = page_text.split("Supporting evidence and citations", 1)[1]
                assert "[S" in following, "An evidence heading was orphaned from its sources."

