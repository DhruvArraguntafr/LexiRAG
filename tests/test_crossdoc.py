from dataclasses import replace
from unittest.mock import patch

import pytest

from backend.container import Services
from core.comparison_plan import is_comparison, plan_comparison, resolve_comparison_documents
from core.comparison_retriever import ComparisonRetriever, balanced_sources
from core.document_comparison import DocumentComparator, comparison_coverage
from core.models import EvidenceRef, Finding, GroundedAnswer, LexiRAGError, SearchFilters
from tests.conftest import ExtractiveTestGenerator, make_pdf


@pytest.mark.parametrize("question",[
    "Compare the consent and notice requirements.",
    "What are the differences between the agreements?",
    "How does liability differ across both documents?",
    "Contrast termination rules versus payment duties.",
])
def test_comparison_detection(question):
    assert is_comparison(question)
    assert not is_comparison("What is the definition of consent?")


def test_split_happens_before_keyword_cleanup():
    plan=plan_comparison("Compare privacy consent and termination notice.")
    assert "privacy consent" in plan.concepts
    assert "termination notice" in plan.concepts
    assert len(plan.concepts)>=3
    assert any("affirmative" in q for q in plan.expanded)
    assert "Rule 4(5)" in plan_comparison("Compare Rule 4(5) and Article 21").concepts[-1]


def test_shorthand_resolution_stays_in_selection(populated):
    populated.upload("Extra Advisory.pdf",make_pdf(["Recommendations on fair commercial conduct."]))
    docs=populated.db.documents()
    # Explicit file aliases and unique instrument shorthand may select a pair.
    ids=tuple(d["id"] for d in docs)
    expected={d["id"] for d in docs if d["name"] in {"Privacy.pdf","Agreement.pdf"}}
    assert set(resolve_comparison_documents(populated.db,ids,"Compare Privacy.pdf and the Agreement"))==expected
    allowed=tuple(d["id"] for d in docs if d["name"]!="Agreement.pdf")
    assert set(resolve_comparison_documents(populated.db,allowed,"Compare Privacy.pdf and Agreement.pdf"))<=set(allowed)


def test_each_concept_uses_independent_scoped_hybrid(populated):
    docs=populated.db.documents()
    ids=[d["id"] for d in docs]
    filters=SearchFilters(tuple(ids),jurisdiction="India",date_from="2024-01-01")
    with patch.object(populated.retriever,"retrieve",wraps=populated.retriever.retrieve) as search:
        result=ComparisonRetriever(populated).retrieve(ids,"Compare privacy consent and termination notice",filters=filters,rerank=False)
    assert len(search.call_args_list)>=len(ids)*3
    for call in search.call_args_list:
        scope=call.kwargs["filters"]
        assert len(scope.document_ids)==1 and set(scope.document_ids)<=set(ids)
        assert scope.jurisdiction=="India" and scope.date_from=="2024-01-01"
        assert call.kwargs["mode"]=="hybrid"
    excluded=next(d["id"] for d in docs if d["jurisdiction"]=="Delhi")
    assert result.groups[excluded]==[]


def test_reranker_actually_executes_and_falls_back(populated,monkeypatch):
    ids=[d["id"] for d in populated.db.documents()]
    class Reranker:
        def __init__(self): self.pairs=[]
        def predict(self,pairs,**kwargs):
            self.pairs.extend(pairs)
            return [float("consent" in text.lower()) for question,text in pairs]
    model=Reranker()
    monkeypatch.setattr("core.comparison_retriever.AUTO_RERANK",True)
    with patch("core.comparison_retriever.load_reranker",return_value=model):
        result=ComparisonRetriever(populated).retrieve(ids,"Compare privacy consent and termination notice")
    assert result.reranked and model.pairs
    assert all(result.anchors[identifier] for identifier in ids)
    with patch("core.comparison_retriever.load_reranker",side_effect=RuntimeError("Private text")):
        fallback=ComparisonRetriever(populated).retrieve(ids,"Compare privacy and termination")
    assert not fallback.reranked and all(fallback.anchors.values())


def test_balanced_context_and_adjacent_passages(populated):
    ids=[d["id"] for d in populated.db.documents()]
    result=ComparisonRetriever(populated).retrieve(ids,"Compare privacy and termination",k=1,rerank=False)
    sources=balanced_sources(result,1800)
    assert {h.chunk.document_id for h in sources.values()}==set(ids)
    for hit in sources.values():
        original=populated.db.chunk(hit.chunk.id)
        assert hit.chunk.text in original.text and hit.chunk.page==original.page
    with pytest.raises(LexiRAGError,match="outside"):
        ComparisonRetriever(populated).retrieve(ids,"Compare privacy",filters=SearchFilters((ids[0],)))


def test_expansion_is_bounded_and_preserves_filters(populated):
    ids=[d["id"] for d in populated.db.documents()]
    filters=SearchFilters(tuple(ids),jurisdiction="India")
    with patch.object(populated.retriever,"retrieve",wraps=populated.retriever.retrieve) as search:
        ComparisonRetriever(populated).retrieve(ids,"Compare consent and termination notice",expanded=True,filters=filters,rerank=False)
    assert any("affirmative" in call.args[0] for call in search.call_args_list)
    assert all(call.kwargs["filters"].jurisdiction=="India" for call in search.call_args_list)


def test_weak_relevance_retries_before_generation(populated):
    populated.upload("Additional privacy.pdf",make_pdf([
        "Section 3 Consent\nA written consent record must identify the purpose and processing period.",
        "Section 4 Notice\nNotice is required before changing any consent processing purpose.",
        "Section 5 Complaints\nA person may submit a complaint and request review of privacy decisions.",
    ]))
    ids=[d["id"] for d in populated.db.documents()]
    class WeakReranker:
        def predict(self,pairs,**kwargs): return [-2.0]*len(pairs)
    with patch("core.comparison_retriever.load_reranker",return_value=WeakReranker()), patch.object(
        populated.retriever,"retrieve",wraps=populated.retriever.retrieve) as search:
        result=ComparisonRetriever(populated).retrieve(ids,"Compare consent and complaint procedures",rerank=True)
    assert result.reranked
    assert any("complaint filing procedure" in call.args[0] for call in search.call_args_list), [call.args[0] for call in search.call_args_list]
    assert len(search.call_args_list)<=len(ids)*20
    assert all(result.groups.values())


def test_faiss_bm25_and_explicit_reference_all_execute(service):
    from core.keyword_search import keyword_search
    service.upload("Statute.pdf",make_pdf(["Article 21 Personal liberty\nNo person shall be deprived of personal liberty except according to procedure established by law."]),"Act / Statute")
    service.upload("Rules.pdf",make_pdf(["Rule 4(5) Complaint procedure\nThe officer shall acknowledge a complaint within the stated period after receipt."]),"Act / Statute")
    ids=[d["id"] for d in service.db.documents()]
    with patch.object(service.vectors,"search",wraps=service.vectors.search) as vectors, patch(
        "core.hybrid_retriever.keyword_search",wraps=keyword_search) as keyword:
        result=ComparisonRetriever(service).retrieve(ids,"Compare Article 21 and Rule 4(5)",k=1,rerank=False)
    assert vectors.call_count>=len(ids) and keyword.call_count>=len(ids)
    assert all(group[0].scores.get("exact_reference")==1.0 for group in result.anchors.values())
    expanded=ComparisonRetriever(service).retrieve(ids,"Compare Article 21 and Rule 4(5) complaint procedures",k=1,rerank=False,expanded=True)
    assert all(group[0].scores.get("exact_reference")==1.0 for group in expanded.anchors.values())


class JointGenerator(ExtractiveTestGenerator):
    def generate(self,question,sources,instruction=""):
        self.calls.append((question,sources,instruction))
        seen={}
        for sid,hit in sources.items(): seen.setdefault(hit.chunk.document_id,(sid,hit))
        return GroundedAnswer(insufficient_evidence=False,findings=[Finding(
            heading="Compared obligations",statement="The passages describe the respective contractual duties.",kind="interpretation",
            evidence=[EvidenceRef(source_id=sid,quote=hit.chunk.text[:100]) for sid,hit in seen.values()])],limitations=[])


def test_merely_separate_summaries_are_not_complete(populated):
    ids=[d["id"] for d in populated.db.documents()]
    generator=ExtractiveTestGenerator()
    result=DocumentComparator(populated,generator).compare(ids,"Compare privacy and termination")
    assert result.answer.insufficient_evidence
    assert len(generator.calls)==2  # bounded expanded-evidence recovery
    assert "paired comparison" in " ".join(result.answer.limitations)


def test_ai_research_preserves_verified_multi_document_answers(populated):
    generator=JointGenerator()
    services=Services(populated.settings,populated.embeddings,generator)
    try:
        workspace=services.workspaces.create("Scoped comparisons")
        ids=[d["id"] for d in populated.db.documents()]
        for identifier in ids: services.workspaces.attach(workspace,identifier)
        run,result=services.research.ask(workspace,"Compare privacy consent and complaint procedures",selected=ids)
        assert comparison_coverage(result,ids)[0]
        assert result.citation_attempts==result.citation_valid>=2
        assert services.workspaces.runs(workspace)[0]["kind"]=="comparison"
        assert not hasattr(services.research, "compare")
        assert all("Separate summaries" in instruction for _,_,instruction in generator.calls)
    finally:
        services.close()


def test_single_source_relational_claim_withheld(populated):
    class Misleading(ExtractiveTestGenerator):
        def generate(self,question,sources,instruction=""):
            answer=super().generate(question,sources,instruction)
            return answer.model_copy(update={"findings":[f.model_copy(update={"statement":"Both documents impose the same duty."}) for f in answer.findings]})
    result=DocumentComparator(populated,Misleading()).compare([d["id"] for d in populated.db.documents()],"Compare duties")
    assert result.answer.insufficient_evidence and not result.answer.findings
    assert "covered only one" in " ".join(result.answer.limitations)


def test_optional_bad_claim_does_not_refuse_valid_paired_findings(populated):
    class ExtraClaim(JointGenerator):
        def generate(self,question,sources,instruction=""):
            answer=super().generate(question,sources,instruction)
            sid,hit=next(iter(sources.items()))
            bad=Finding(heading="Extra",statement="Both documents state an identical requirement.",kind="interpretation",
                        evidence=[EvidenceRef(source_id=sid,quote=hit.chunk.text[:100])])
            return answer.model_copy(update={"findings":[*answer.findings,bad]})
    ids=[d["id"] for d in populated.db.documents()]
    result=DocumentComparator(populated,ExtraClaim()).compare(ids,"Compare duties")
    assert not result.answer.insufficient_evidence
    assert len(result.answer.findings)==1
    assert comparison_coverage(result,ids)[0]
    assert "withheld" in " ".join(result.answer.limitations)
