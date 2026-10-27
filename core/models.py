from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class LexiRAGError(Exception):
    """An actionable error safe to present without document contents or credentials."""


@dataclass
class Chunk:
    id: str
    document_id: str
    document_name: str
    page: int
    text: str
    locator: str | None = None
    ordinal: int = 0


@dataclass
class SearchHit:
    chunk: Chunk
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchFilters:
    document_ids: tuple[str, ...] = ()
    document_type: str | None = None
    jurisdiction: str | None = None
    date_from: str | None = None
    date_to: str | None = None


class EvidenceRef(BaseModel):
    source_id: str = Field(description="An exact source label from the supplied evidence, e.g. S1")
    quote: str = Field(min_length=12, description="A verbatim supporting excerpt from that source")


class Finding(BaseModel):
    heading: str = Field(description="Short heading for one independent point. Include the explicitly supported provision number when the question asks for it. Each item of a requested list has its own finding.")
    statement: str = Field(description="A concise explanation without inline citations or invented quotations")
    kind: Literal["fact", "interpretation"]
    evidence: list[EvidenceRef] = Field(min_length=1)


class GroundedAnswer(BaseModel):
    insufficient_evidence: bool
    findings: list[Finding]
    limitations: list[str]


@dataclass
class ResearchResult:
    question: str
    answer: GroundedAnswer
    sources: dict[str, SearchHit]
    latency_seconds: float = 0.0
    mode: str = "hybrid"
    # Retained for multi-document AI Research and historical report exports.
    comparison_rows: list[dict] = field(default_factory=list)
    # Structural provenance only: this is NOT a measure of semantic entailment.
    citation_attempts: int = 0
    citation_valid: int = 0

