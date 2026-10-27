from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.container import Services
from core.legal_sections import LegalIndex, SectionTracker, references, query_variants
from core.models import EvidenceRef, Finding, GroundedAnswer, SearchFilters
from core.rag_pipeline import RAGPipeline
from core.service import CorpusService
from tests.conftest import TestEmbeddings, make_pdf

QUESTION = "What are the six consumer rights under the Consumer Protection Act, 2019? Explain them in simple language and cite the relevant section."
EXCERPT = Path("tests/fixtures/consumer_rights_verified.txt").read_text(encoding="utf-8")


@pytest.fixture
def act(settings):
    service = CorpusService(replace(settings, context_chars=12000), TestEmbeddings())
    left, right = EXCERPT.split("(iii)", 1)
    document = service.upload("Verified-consumer-rights-excerpt.pdf", make_pdf([left, "(iii)" + right]), "Act / Statute", "India", "2019-08-09")
    return service, document["id"]


@pytest.mark.parametrize("question,expected", [
    ("Section 2 ( 9 )", "section:2(9)"), ("Rule 4(5)", "rule:4(5)"),
    ("Article 21", "article:21"), ("Art. 21A", "article:21a"),
])
def test_reference_normalization(question, expected):
    assert references(question) == [expected]


def test_amendment_footnote_does_not_reset_rule_on_next_page():
    tracker = SectionTracker("rule")
    tracker.spans("4. Duties of entities\n(1) A requirement applies.\n2. Subs. by a notification.")
    spans = tracker.spans("(5) The grievance officer must respond to complaints.")
    assert spans[0].reference == "rule:4(5)"


def test_longer_defined_term_is_not_diluted_by_its_substring(act):
    service, _ = act
    service.upload("Extra.pdf", make_pdf(['Section 2 Definitions\n(7) "consumer" means a person who buys goods.']), "Act / Statute")
    hits = service.retriever.retrieve(QUESTION, k=2)
    assert "consumer rights" in hits[0].chunk.text


def test_general_topic_does_not_force_single_word_definition(act):
    service, _ = act
    service.upload("Definitions.pdf", make_pdf(['Section 2 Definitions\n(7) "consumer" means a person who buys goods.']), "Act / Statute")
    index = LegalIndex(service.db, service.db.chunks())
    assert not index.lookup("How do consumer complaints get resolved?")[1]
    assert index.lookup("What is a consumer?")[1]


def test_numbered_provision_continues_on_next_page(act):
    service, document_id = act
    chunks = service.db.chunks(SearchFilters(document_ids=(document_id,)))
    assert all("Section 2(9)" in c.locator for c in chunks if "(iii)" in c.text)
    assert any("(iv)" in c.text and "(v)" in c.text and "(vi)" in c.text for c in chunks)
    assert all(c.page in {1, 2} for c in chunks)


def test_consumer_question_retrieves_all_six_verified_clauses(act):
    service, document_id = act
    hits = service.retriever.retrieve(QUESTION, filters=SearchFilters(document_ids=(document_id,)))
    text = " ".join(h.chunk.text for h in hits)
    for item in ("(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)"):
        assert item in text
    assert any("Section 2(9)" in h.chunk.locator for h in hits)
    _, ids = service.vectors.load()
    assert all(h.chunk.id in ids for h in hits)


def test_legacy_page_repair_preserves_chunks_vectors_and_saved_records(act):
    service, document_id = act
    before = [(c.id, c.text) for c in service.db.chunks()]
    _, ids = service.vectors.load()
    with service.db.connect() as con:
        con.execute("DELETE FROM document_pages WHERE document_id=?", (document_id,))
    index = LegalIndex(service.db, service.db.chunks())
    assert index.by_reference["section:2(9)"]
    assert service.db.page(document_id, 2)
    assert before == [(c.id, c.text) for c in service.db.chunks()]
    assert service.vectors.load()[1] == ids


def test_exact_rule_and_article_lookup_does_not_confuse_prefixes(service):
    doc = service.upload("Rules.pdf", make_pdf([
        "Rule 4 Duties\n(5) A seller shall publish contact details for complaints.\n(6) Other duties apply.",
        "Article 21 Protection\nNo person shall be deprived of life or personal liberty except according to procedure established by law.\nArticle 211 Other matters\nThis is a different article."
    ]))
    f = SearchFilters(document_ids=(doc["id"],))
    assert "Rule 4(5)" in service.retriever.retrieve("Rule 4 (5)", k=1, filters=f)[0].chunk.locator
    assert "Article 211" not in service.retriever.retrieve("Article 21", k=1, filters=f)[0].chunk.locator


def test_recovery_stays_inside_document_metadata_and_workspace_filters(act):
    service, document_id = act
    other = service.upload("Unrelated.pdf", make_pdf(["Section 2 Privacy\nThis document only discusses privacy duties."]), jurisdiction="Delhi")
    filters = SearchFilters(document_ids=(other["id"],), jurisdiction="Delhi")
    assert all(h.chunk.document_id == other["id"] for h in service.retriever.broaden(QUESTION, filters))
    assert not service.retriever.broaden(QUESTION, SearchFilters(document_ids=(document_id,), jurisdiction="Delhi"))
    platform = Services(service.settings, service.embeddings)
    try:
        ws = platform.workspaces.create("Unrelated collection")
        platform.workspaces.attach(ws, other["id"])
        with pytest.raises(Exception, match="outside"):
            platform.research.ask(ws, QUESTION, selected=[document_id])
    finally:
        platform.close()


def test_refusal_causes_one_expanded_evidence_attempt(act):
    service, document_id = act
    initial = service.retriever.retrieve(QUESTION, filters=SearchFilters(document_ids=(document_id,)))[:1]
    expanded = service.retriever.broaden(QUESTION, SearchFilters(document_ids=(document_id,)), initial)
    class Generator:
        def __init__(self):
            self.calls = 0
        def generate(self, question, sources, instruction=""):
            self.calls += 1
            if self.calls == 1:
                return GroundedAnswer(insufficient_evidence=True, findings=[], limitations=["Incomplete list"])
            findings = []
            for sid, hit in sources.items():
                for line in hit.chunk.text.splitlines():
                    if line.strip().startswith(tuple(f"({x})" for x in ("i", "ii", "iii", "iv", "v", "vi"))):
                        findings.append(Finding(heading="Verified clause", statement="The supplied clause supports this right.", kind="fact", evidence=[EvidenceRef(source_id=sid, quote=line.strip())]))
            return GroundedAnswer(insufficient_evidence=False, findings=findings, limitations=[])
    generator = Generator()
    with patch.object(service.retriever, "retrieve", return_value=initial), patch.object(service.retriever, "broaden", return_value=expanded):
        result = RAGPipeline(service, generator).research(QUESTION, filters=SearchFilters(document_ids=(document_id,)))
    assert generator.calls == 2
    assert not result.answer.insufficient_evidence
    assert result.citation_valid == result.citation_attempts > 0


def test_no_new_evidence_does_not_repeat_model_call(act):
    service, document_id = act
    class Generator:
        calls = 0
        def generate(self, *args):
            self.calls += 1
            return GroundedAnswer(insufficient_evidence=True, findings=[], limitations=["Not covered"])
    generator = Generator()
    hits = service.retriever.retrieve(QUESTION)
    with patch.object(service.retriever, "retrieve", return_value=hits), patch.object(service.retriever, "broaden", return_value=hits):
        result = RAGPipeline(service, generator).research(QUESTION)
    assert result.answer.insufficient_evidence and generator.calls == 1


@pytest.mark.parametrize("initial_insufficient", [True, False])
def test_comparison_recovers_independently_within_each_document(act, initial_insufficient):
    from core.document_comparison import DocumentComparator
    service, act_id = act
    other = service.upload("Other.pdf", make_pdf(["Section 4 Duties\nA provider shall publish contact details for consumer complaints."]))
    class Generator:
        calls = 0
        def generate(self, question, sources, instruction=""):
            self.calls += 1
            if self.calls == 1:
                sid, hit = next(iter(sources.items()))
                return GroundedAnswer(insufficient_evidence=initial_insufficient, findings=[Finding(
                    heading="One document only", statement="This source addresses a point.", kind="fact",
                    evidence=[EvidenceRef(source_id=sid, quote=hit.chunk.text[:80])])], limitations=[])
            return GroundedAnswer(insufficient_evidence=False, findings=[Finding(
                heading="Supported comparison", statement="The supplied documents address different matters.", kind="interpretation",
                evidence=[EvidenceRef(source_id=sid, quote=hit.chunk.text[:80]) for sid,hit in sources.items()])], limitations=[])
    generator = Generator()
    result = DocumentComparator(service, generator).compare([act_id, other["id"]], "Compare consumer rights and duties", k=1)
    assert generator.calls == 2
    assert not result.answer.insufficient_evidence
    assert {h.chunk.document_id for h in result.sources.values()} == {act_id, other["id"]}


def test_comparison_with_only_one_cited_document_remains_incomplete(act):
    from core.document_comparison import DocumentComparator
    service, act_id = act
    other = service.upload("Other.pdf", make_pdf(["Section 4 Duties\nA provider shall publish contact details for complaints."]))
    class Generator:
        def generate(self, question, sources, instruction=""):
            sid, hit = next(iter(sources.items()))
            return GroundedAnswer(insufficient_evidence=False, findings=[Finding(
                heading="One source", statement="This one source supports a fact.", kind="fact",
                evidence=[EvidenceRef(source_id=sid, quote=hit.chunk.text[:80])])], limitations=[])
    result = DocumentComparator(service, Generator()).compare([act_id, other["id"]], "Compare the documents", k=1)
    assert result.answer.insufficient_evidence
    assert any("every selected document" in item for item in result.answer.limitations)


def test_diagnostics_contain_identifiers_but_no_source_text(act):
    service, _ = act
    with patch("core.retrieval_diagnostics.LOGGER.info") as logger:
        hits = service.retriever.retrieve(QUESTION)
    payload = json.loads(logger.call_args.args[0])
    assert payload["question"] == QUESTION
    assert payload["chunks"][0]["id"] == hits[0].chunk.id
    assert "text" not in payload["chunks"][0]
    assert "hazardous to life" not in logger.call_args.args[0]


def test_query_expansion_is_general_and_preserves_requested_reference():
    assert "consumer rights" in query_variants(QUESTION)[0]
    assert "Rule 4(5)" in query_variants("Explain Rule 4(5) in simple language")
