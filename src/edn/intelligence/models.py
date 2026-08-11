"""Source-neutral contracts for bounded intelligence retrieval and responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from edn.intelligence.action_models import ActionProposal

from edn.core import (
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
)


class StatementKind(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"
    PROPOSED_ACTION = "proposed_action"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    query: str
    principal: PrincipalContext
    purpose: Purpose
    security_domain: SecurityDomain
    classification: Classification
    resource_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be blank")
        if not self.principal.allows_domain(self.security_domain):
            raise ValueError("requested domain is not active for this principal")


@dataclass(frozen=True, slots=True)
class ContextEvidence:
    """Bounded private evidence with durable, source-owned provenance."""

    context_id: str
    capability_id: str
    source_label: str
    title: str
    excerpt: str
    score: float
    provenance: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.context_id or not self.capability_id:
            raise ValueError("context and capability IDs must not be blank")
        if not self.source_label.strip() or not self.title.strip():
            raise ValueError("source label and title must not be blank")
        if not self.excerpt.strip() or len(self.excerpt) > 2_000:
            raise ValueError("evidence excerpt must be bounded and nonblank")
        if not self.provenance:
            raise ValueError("private evidence requires provenance")


@dataclass(frozen=True, slots=True)
class GlobalKnowledge:
    """Explicit non-private model knowledge; it can never be cited as evidence."""

    knowledge_id: str
    text: str
    source_label: str = "general model knowledge"

    def __post_init__(self) -> None:
        if not self.knowledge_id or not self.text.strip():
            raise ValueError("global knowledge ID and text must not be blank")


@dataclass(frozen=True, slots=True)
class IntelligenceStatement:
    kind: StatementKind
    text: str
    evidence_ids: tuple[str, ...] = ()
    global_knowledge_ids: tuple[str, ...] = ()
    confidence: str = "unknown"

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("statement text must not be blank")
        if self.kind is StatementKind.FACT and not self.evidence_ids:
            raise ValueError("facts require private evidence")
        if self.kind is StatementKind.UNKNOWN and (
            self.evidence_ids or self.global_knowledge_ids
        ):
            raise ValueError("unknown statements must not claim supporting sources")
        if self.kind is StatementKind.FACT and self.global_knowledge_ids:
            raise ValueError("global knowledge must not be represented as private fact")


@dataclass(frozen=True, slots=True)
class AssembledContext:
    request: IntelligenceRequest
    evidence: tuple[ContextEvidence, ...]
    unavailable_capabilities: tuple[str, ...]
    global_knowledge: tuple[GlobalKnowledge, ...] = ()


@dataclass(frozen=True, slots=True)
class IntelligencePriority:
    title: str
    why_it_matters: str
    evidence_ids: tuple[str, ...]
    timeframe: str | None
    confidence: str
    recommended_next_step: str
    missing_information: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.why_it_matters.strip():
            raise ValueError("priority title and rationale must not be blank")
        if not self.evidence_ids:
            raise ValueError("priority requires private evidence")


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    statements: tuple[IntelligenceStatement, ...]
    evidence: tuple[ContextEvidence, ...]
    global_knowledge: tuple[GlobalKnowledge, ...]
    unavailable_capabilities: tuple[str, ...]
    session_id: str
    priorities: tuple[IntelligencePriority, ...] = ()
    proposed_actions: tuple[ActionProposal, ...] = ()

    @property
    def source_families(self) -> tuple[str, ...]:
        return tuple(sorted({item.source_label for item in self.evidence}))
