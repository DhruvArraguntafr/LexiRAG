"""Comparison excerpt selection: source text is copied by code, not retyped by AI."""
from typing import Literal

from pydantic import BaseModel, Field

from core.models import EvidenceRef, Finding, GroundedAnswer


class ExcerptSelection(BaseModel):
    source_id: str = Field(description="Exact supplied source_id")
    excerpt_id: str = Field(description="Exact excerpt_id belonging to that source, e.g. S1.Q1")


class SelectedFinding(BaseModel):
    heading: str
    statement: str = Field(description="Explain the supported point in simple language, without invented citations")
    kind: Literal["fact", "interpretation"]
    evidence: list[ExcerptSelection] = Field(min_length=1)


class SelectedAnswer(BaseModel):
    insufficient_evidence: bool
    findings: list[SelectedFinding]
    limitations: list[str]


def prepare_excerpts(sources, size=650):
    """Partition retrieved chunks into contiguous, page-local quoting choices.

    No concatenation across chunks, OCR correction, additional page retrieval,
    or duplicated full context. Bindings retain exact original substrings.
    """
    evidence, bindings = [], {}
    for sid, hit in sources.items():
        text, start, choices = hit.chunk.text, 0, []
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                split = text.rfind("\n", start + size // 2, end)
                if split < 0:
                    split = text.rfind(" ", start + size // 2, end)
                if split > start:
                    end = split
            if len(text[end:].strip()) < 12:
                end = len(text)
            quote = text[start:end].strip()
            if len(quote) >= 12:
                identifier = f"{sid}.Q{len(choices) + 1}"
                bindings[identifier] = (sid, quote)
                choices.append({"excerpt_id": identifier, "text": quote})
            start = end
        evidence.append({"source_id": sid, "document": hit.chunk.document_name,
                         "document_id": hit.chunk.document_id, "pdf_page": hit.chunk.page,
                         "locator": hit.chunk.locator, "excerpts": choices})
    return evidence, bindings


def resolve_selections(answer, sources, bindings):
    """Only selected, source-owned excerpts become citations; fail closed otherwise.

    Unavailable selections become invalid refs for the usual whole-finding
    citation validator to reject and count, rather than silently dropping refs.
    """
    missing = "__unavailable_excerpt__"
    while missing in sources:
        missing += "_"
    findings = []
    for finding in answer.findings:
        refs = []
        for selected in finding.evidence:
            binding = bindings.get(selected.excerpt_id)
            if binding and binding[0] == selected.source_id and selected.source_id in sources:
                refs.append(EvidenceRef(source_id=selected.source_id, quote=binding[1]))
            else:
                refs.append(EvidenceRef(source_id=missing, quote="The selected source excerpt is unavailable."))
        findings.append(Finding(heading=finding.heading, statement=finding.statement, kind=finding.kind, evidence=refs))
    return GroundedAnswer(insufficient_evidence=answer.insufficient_evidence, findings=findings, limitations=answer.limitations)
