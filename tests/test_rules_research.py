from pathlib import Path
from unittest.mock import patch

import pytest

from core.legal_sections import LegalIndex, SectionTracker, asks_definition_of, named_documents, query_variants
from core.models import SearchFilters
from tests.conftest import make_pdf

QUESTION = "Under the Consumer Protection (E-Commerce) Rules, 2020, what is the time limit for acknowledging and resolving consumer complaints? Explain the relevant rule and provide citations from the uploaded document."
CONTROL = "Under the Consumer Protection (E-Commerce) Rules, 2020, may consent be recorded automatically using pre-ticked checkboxes? Cite the relevant rule."
NAME = "Consumer Protection (E-Commerce) Rules, 2020.pdf"
TEXT = Path("tests/fixtures/ecommerce_rules_verified.txt").read_text(encoding="utf-8")


@pytest.fixture
def rules(service):
    identifier = service.upload(NAME, make_pdf([TEXT]))["id"]
    service.upload("Definitions.pdf", make_pdf(['Section 2 Definitions\n(7) "consumer" means a buyer.\n(16) "e-commerce" means electronic transactions.']), "Act / Statute")
    return service, identifier


def test_deadline_question_does_not_activate_consumer_definition(rules):
    service, _ = rules
    index = LegalIndex(service.db, service.db.chunks())
    assert not asks_definition_of(QUESTION, "consumer")
    assert not index.lookup(QUESTION)[1]
    assert asks_definition_of("What is a consumer?", "consumer")
    assert asks_definition_of("Define the consumer under this Act.", "consumer")
    assert not asks_definition_of("What is the duty of a consumer?", "consumer")


def test_focal_query_removes_rules_title_and_answer_instructions():
    variants = query_variants(QUESTION)
    assert variants[0] == "time limit acknowledging resolving consumer complaints"
    assert not any("definition" in q for q in variants)


def test_named_instrument_has_priority_without_changing_document_filters(rules):
    service, identifier = rules
    assert named_documents(QUESTION, service.db.documents()) == {identifier}
    hits = service.retriever.retrieve(QUESTION)
    assert hits[0].chunk.document_id == identifier
    assert "one month" in " ".join(h.chunk.text for h in hits)
    excluded = next(d["id"] for d in service.db.documents() if d["id"] != identifier)
    filtered = service.retriever.retrieve(QUESTION, filters=SearchFilters(document_ids=(excluded,)))
    assert all(h.chunk.document_id == excluded for h in filtered)
    # Even a stale caller's broader initial pool cannot escape a retry filter.
    recovered = service.retriever.broaden(QUESTION, SearchFilters(document_ids=(excluded,)), hits)
    assert all(h.chunk.document_id == excluded for h in recovered)
    assert not service.retriever.broaden(QUESTION, SearchFilters(document_ids=(identifier,), jurisdiction="Excluded"))


def test_complete_original_deadline_provision_is_retrieved(rules):
    service, identifier = rules
    hits = service.retriever.retrieve(QUESTION, filters=SearchFilters(document_ids=(identifier,)))
    text = " ".join(h.chunk.text for h in hits)
    assert "forty-" in text and "eight hours" in text and "one month from the date of receipt" in text
    assert any("Rule 4(5)" in (h.chunk.locator or "") for h in hits)
    _, ids = service.vectors.load()
    assert all(h.chunk.id in ids for h in hits)


def test_second_rules_question_retrieves_consent_provision(rules):
    service, identifier = rules
    hits = service.retriever.retrieve(CONTROL)
    assert hits[0].chunk.document_id == identifier
    assert any("pre-ticked checkboxes" in h.chunk.text and "Rule 4(9)" in h.chunk.locator for h in hits)


@pytest.mark.parametrize("header", ["4. Duties", "4.Duties", "4 . Duties"])
def test_ocr_heading_spacing_does_not_lose_rule_reference(header):
    tracker = SectionTracker("rule")
    spans = tracker.spans(header + "\n(5)Every entity must follow the stated procedure.")
    assert spans[-1].reference == "rule:4(5)"


def test_generic_filename_does_not_match_every_question():
    assert not named_documents(QUESTION, [{"id":"a", "name":"Rules.pdf"}, {"id":"b","name":"Act.pdf"}])


def test_other_explicitly_selected_document_never_searches_named_rules(rules):
    service, identifier = rules
    other = next(d["id"] for d in service.db.documents() if d["id"] != identifier)
    with patch.object(service.embeddings, "embed_query", wraps=service.embeddings.embed_query) as query:
        hits = service.retriever.retrieve(QUESTION, filters=SearchFilters(document_ids=(other,)))
    assert query.call_count >= 2
    assert all(h.chunk.document_id == other for h in hits)
