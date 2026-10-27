from dataclasses import replace
from unittest.mock import patch

from langchain_core.runnables import RunnableLambda
import pytest

from backend.container import Services
from core.citation_manager import match_quote, normalize, validate_answer, verify_ref
from core.comparison_evidence import SelectedAnswer, prepare_excerpts, resolve_selections
from core.models import Chunk, EvidenceRef, Finding, GroundedAnswer, SearchHit
from core.rag_pipeline import GeminiGenerator
from core.document_comparison import DocumentComparator
from tests.conftest import ExtractiveTestGenerator, make_pdf


@pytest.mark.parametrize("source,quote", [
    ('The “consumer” shall receive a reply—within thirty days.', 'The "consumer" shall receive a reply - within thirty days.'),
    ("Scope and Applicability.—(1) These rules apply to goods.", "Scope and Applicability. — (1) These rules apply to goods."),
    ("The officer\r\nshall acknowledge\u00a0the complaint.", "The officer shall acknowledge the complaint."),
    ("A notiﬁcation shall be issued to the provider.", "A notification shall be issued to the provider."),
    ("The applicable pro-\nvision requires consent.", "The applicable provision requires consent."),
    ("The pro\u00advider must respond to the complaint.", "The provider must respond to the complaint."),
])
def test_formatting_match_returns_original_source_substring(source, quote):
    match = match_quote(quote, source)
    assert match and match.text == source[match.start:match.end]
    hit = SearchHit(Chunk("c", "d", "rules.pdf", 2, source))
    answer = GroundedAnswer(insufficient_evidence=False, findings=[Finding(
        heading="Supported", statement="The source states this requirement.", kind="fact",
        evidence=[EvidenceRef(source_id="S1", quote=quote)])], limitations=[])
    checked, attempts, valid = validate_answer(answer, {"S1": hit})
    assert attempts == valid == 1
    ref = checked.findings[0].evidence[0]
    assert normalize(ref.quote) in normalize(source)
    assert ref.quote == match.text  # downstream saves remain exact matches


@pytest.mark.parametrize("source,quote", [
    ("The officer shall not disclose customer records.", "The officer shall disclose customer records."),
    ("Reply within thirty days after receipt.", "Reply within thirteen days after receipt."),
    ("The fee is Rs. 1,000 for this application.", "The fee is Rs. 1.000 for this application."),
    ("Rule 4(5) governs the grievance procedure.", "Rule 4(6) governs the grievance procedure."),
    ("The fee is 1000 rupees under this rule.", "The fee is 1OOO rupees under this rule."),
    ("The authority is nowhere identified in this document.", "The authority is now here identified in this document."),
    ("All alle-commerce retail activities are covered.", "All all e-commerce retail activities are covered."),
    ("This is unlawful conduct in commerce.", "lawful conduct in commerce."),
    ("The total is -30 rupees after adjustment.", "30 rupees after adjustment."),
    ("The seller must publish the address and phone number.", "The seller must publish ... phone number."),
])
def test_changes_to_legal_content_fail_closed(source, quote):
    assert match_quote(quote, source) is None


def test_unknown_source_or_cross_page_quote_is_rejected():
    sources = {"S1": SearchHit(Chunk("a", "d", "rules.pdf", 2, "The officer must acknowledge complaints.")),
               "S2": SearchHit(Chunk("b", "d", "rules.pdf", 3, "A written decision must follow."))}
    assert not verify_ref(EvidenceRef(source_id="S99", quote="The officer must acknowledge complaints."), sources)
    assert not verify_ref(EvidenceRef(source_id="S2", quote="The officer must acknowledge complaints."), sources)
    assert not verify_ref(EvidenceRef(source_id="S1", quote="The officer must acknowledge complaints. A written decision must follow."), sources)


def test_selected_excerpts_preserve_all_characters_and_page_ownership():
    text = "The “seller” shall reply—within thirty days.\n" * 30 + "(Not now.)"
    sources = {"S1": SearchHit(Chunk("a", "d", "scan.pdf", 4, text)),
               "S2": SearchHit(Chunk("b", "other", "act.pdf", 1, "This Act applies to all goods and services."))}
    payload, bindings = prepare_excerpts(sources)
    assert normalize(" ".join(x["text"] for x in payload[0]["excerpts"])) == normalize(text)
    assert all(quote in sources[sid].chunk.text for sid,quote in bindings.values())
    answer = SelectedAnswer.model_validate({"insufficient_evidence": False, "findings": [{
        "heading": "Comparison", "statement": "A supported comparison.", "kind": "fact",
        "evidence": [{"source_id":"S1","excerpt_id":"S1.Q1"}, {"source_id":"S2","excerpt_id":"S2.Q1"}]}], "limitations": []})
    resolved = resolve_selections(answer, sources, bindings)
    checked, attempts, valid = validate_answer(resolved, sources)
    assert attempts == valid == 2 and not checked.insufficient_evidence
    assert sources[checked.findings[0].evidence[0].source_id].chunk.page == 4
    wrong = answer.model_copy(deep=True)
    wrong.findings[0].evidence[0].source_id = "S2"
    rejected, _, _ = validate_answer(resolve_selections(wrong,sources,bindings), sources)
    assert rejected.insufficient_evidence and not rejected.findings
    wrong.findings[0].evidence[0].excerpt_id = "invented"
    assert not validate_answer(resolve_selections(wrong,sources,bindings),sources)[0].findings


def test_native_gemini_comparison_selects_source_excerpts(settings):
    sources = {"S1":SearchHit(Chunk("a","d","rules.pdf",2,"The “seller” must respond—within thirty days."))}
    response = SelectedAnswer.model_validate({"insufficient_evidence":False,"findings":[{
        "heading":"Response", "statement":"The source sets a response period.","kind":"fact",
        "evidence":[{"source_id":"S1","excerpt_id":"S1.Q1"}]}],"limitations":[]})
    with patch("langchain_google_genai.ChatGoogleGenerativeAI") as model:
        model.return_value.with_structured_output.return_value = RunnableLambda(lambda prompt:response)
        answer = GeminiGenerator(replace(settings,api_key="test-only")).generate_comparison("Compare",sources)
        assert model.return_value.with_structured_output.call_args.args[0] is SelectedAnswer
    assert answer.findings[0].evidence[0].quote == sources["S1"].chunk.text


def test_normalized_quotes_can_be_saved_without_changing_chunks(populated):
    platform=Services(populated.settings,populated.embeddings,ExtractiveTestGenerator())
    try:
        ws=platform.workspaces.create("Comparison validation")
        for doc in platform.corpus.db.documents():platform.workspaces.attach(ws,doc["id"])
        run_id,result=platform.research.ask(ws,"privacy consent")
        before={c.id:c.text for c in platform.corpus.db.chunks()}
        platform.evidence.save_finding(ws,run_id,0)
        assert platform.evidence.findings(ws)[0]["valid_sources"]
        assert before=={c.id:c.text for c in platform.corpus.db.chunks()}
    finally:platform.close()


def test_scope_comparison_includes_extent_and_continuations_only_from_selected_pdfs(service):
    act = service.upload("Teaching-Act.pdf", make_pdf([
        "Section 1 Short title and extent\n(1) This is a fictional teaching instrument.\n"
        "(2) It extends to the teaching region.\n(4) It shall apply to all teaching goods and services."
    ]), "Act / Statute")
    rules = service.upload("Teaching-Rules.pdf", make_pdf([
        "Rule 2 Scope and applicability\nThese teaching rules apply to:\n"
        "(a) online teaching goods and services;\n(b) marketplace and inventory teaching models."
    ]))
    service.upload("Excluded.pdf", make_pdf(["Section 1 Scope and applicability\nA different, excluded document covers unrelated transactions."]))
    generator = ExtractiveTestGenerator()
    result = DocumentComparator(service, generator).compare([act["id"], rules["id"]], "Compare the stated scope of these documents")
    assert {hit.chunk.document_id for hit in result.sources.values()} == {act["id"], rules["id"]}
    text = " ".join(hit.chunk.text for hit in result.sources.values())
    assert "all teaching goods and services" in text and "marketplace and inventory" in text


def test_ocr_highlighting_uses_same_page_and_formatting_match(populated):
    import json
    platform = Services(populated.settings, populated.embeddings, ExtractiveTestGenerator())
    try:
        doc = platform.corpus.db.documents()[0]
        with platform.corpus.db.connect() as con:
            con.execute("UPDATE document_pages SET text=?,method='rapidocr',blocks=? WHERE document_id=? AND page=1",
                        ("Scope and Applicability.—(1) These rules apply.", json.dumps([
                            {"text":"Scope and Applicability.—(1) These rules apply.","bbox":[10,20,200,35],"method":"rapidocr"}
                        ]), doc["id"]))
        rectangles, label = platform.sources.locations(doc["id"], 1, "Scope and Applicability. — (1) These rules apply.")
        assert rectangles == [[10,20,200,35]] and "OCR" in label
    finally:
        platform.close()
