"""Source-neutral contracts for bounded intelligence retrieval and responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


class FreshnessState(StrEnum):
    CURRENT = "current"
    AGEING = "ageing"
    STALE = "stale"
    UNKNOWN = "unknown_freshness"


class BriefSectionKind(StrEnum):
    EXECUTIVE_SUMMARY = "executive_summary"
    IMMEDIATE_ATTENTION = "immediate_attention"
    UPCOMING_COMMITMENTS = "today_upcoming_commitments"
    RECENT_COMMUNICATIONS = "recent_communications_commitments"
    PROJECT_CONTEXT = "project_operational_context"
    RISKS_GAPS = "risks_gaps_stale_evidence"
    SUGGESTED_ACTIONS = "suggested_internal_actions_decisions"


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
    source_timestamp: datetime | None = None
    timestamp_kind: str | None = None

    def __post_init__(self) -> None:
        if not self.context_id or not self.capability_id:
            raise ValueError("context and capability IDs must not be blank")
        if not self.source_label.strip() or not self.title.strip():
            raise ValueError("source label and title must not be blank")
        if not self.excerpt.strip() or len(self.excerpt) > 2_000:
            raise ValueError("evidence excerpt must be bounded and nonblank")
        if not self.provenance:
            raise ValueError("private evidence requires provenance")
        if self.source_timestamp is not None and self.source_timestamp.tzinfo is None:
            raise ValueError("source timestamp must be timezone-aware")
        if (self.source_timestamp is None) != (self.timestamp_kind is None):
            raise ValueError(
                "source timestamp and timestamp kind must be declared together"
            )


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
class DailyBriefItem:
    item_id: str
    section: BriefSectionKind
    kind: StatementKind
    title: str
    text: str
    evidence_ids: tuple[str, ...]
    freshness: FreshnessState
    rank_score: int
    rank_reasons: tuple[str, ...]
    proposal_only: bool = False

    def __post_init__(self) -> None:
        if not self.item_id or not self.title.strip() or not self.text.strip():
            raise ValueError("brief item identity and content must not be blank")
        if self.kind is StatementKind.FACT and not self.evidence_ids:
            raise ValueError("brief facts require evidence")
        if self.kind is StatementKind.UNKNOWN and self.evidence_ids:
            raise ValueError("brief gaps must not claim supporting evidence")
        if self.rank_score < 0:
            raise ValueError("brief rank score must not be negative")
        if self.proposal_only and self.kind not in {
            StatementKind.RECOMMENDATION,
            StatementKind.PROPOSED_ACTION,
        }:
            raise ValueError("proposal-only items must be recommendations or proposals")


@dataclass(frozen=True, slots=True)
class DailyBriefSection:
    kind: BriefSectionKind
    title: str
    items: tuple[DailyBriefItem, ...]


@dataclass(frozen=True, slots=True)
class DailyIntelligenceBrief:
    generated_at: datetime
    sections: tuple[DailyBriefSection, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("brief generation time must be timezone-aware")
        expected = tuple(BriefSectionKind)
        if tuple(section.kind for section in self.sections) != expected:
            raise ValueError(
                "brief sections must use the canonical deterministic order"
            )

    @property
    def items(self) -> tuple[DailyBriefItem, ...]:
        return tuple(item for section in self.sections for item in section.items)


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    statements: tuple[IntelligenceStatement, ...]
    evidence: tuple[ContextEvidence, ...]
    global_knowledge: tuple[GlobalKnowledge, ...]
    unavailable_capabilities: tuple[str, ...]
    session_id: str
    priorities: tuple[IntelligencePriority, ...] = ()
    proposed_actions: tuple[ActionProposal, ...] = ()
    daily_brief: DailyIntelligenceBrief | None = None

    @property
    def source_families(self) -> tuple[str, ...]:
        return tuple(sorted({item.source_label for item in self.evidence}))
