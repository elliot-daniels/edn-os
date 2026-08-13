"""Freshness-aware deterministic Daily Intelligence composition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from edn.intelligence.models import (
    AssembledContext,
    BriefSectionKind,
    ContextEvidence,
    DailyBriefItem,
    DailyBriefSection,
    DailyIntelligenceBrief,
    FreshnessState,
    IntelligencePriority,
    StatementKind,
)


@dataclass(frozen=True, slots=True)
class SourceBriefPolicy:
    """Declared value and freshness policy for one exact source capability."""

    capability_id: str
    current_for: timedelta
    stale_after: timedelta
    decision_usefulness: int
    recurrence: int
    evidence_quality: int
    section: BriefSectionKind

    def __post_init__(self) -> None:
        if not self.capability_id or self.current_for < timedelta(0):
            raise ValueError("source freshness policy must be valid")
        if self.stale_after <= self.current_for:
            raise ValueError("stale threshold must follow current threshold")
        for value in (
            self.decision_usefulness,
            self.recurrence,
            self.evidence_quality,
        ):
            if not 1 <= value <= 5:
                raise ValueError("source value factors must be between one and five")


DEFAULT_SOURCE_POLICIES = (
    SourceBriefPolicy(
        "calendar.search",
        timedelta(days=1),
        timedelta(days=7),
        5,
        5,
        5,
        BriefSectionKind.UPCOMING_COMMITMENTS,
    ),
    SourceBriefPolicy(
        "outlook.search",
        timedelta(days=1),
        timedelta(days=7),
        5,
        5,
        5,
        BriefSectionKind.RECENT_COMMUNICATIONS,
    ),
    SourceBriefPolicy(
        "local-files.search",
        timedelta(days=7),
        timedelta(days=30),
        4,
        4,
        5,
        BriefSectionKind.PROJECT_CONTEXT,
    ),
    SourceBriefPolicy(
        "email.retrieve",
        timedelta(days=7),
        timedelta(days=30),
        3,
        4,
        4,
        BriefSectionKind.RECENT_COMMUNICATIONS,
    ),
    SourceBriefPolicy(
        "knowledge.retrieve",
        timedelta(days=7),
        timedelta(days=30),
        3,
        3,
        3,
        BriefSectionKind.PROJECT_CONTEXT,
    ),
)

_SECTION_TITLES = {
    BriefSectionKind.EXECUTIVE_SUMMARY: "Executive summary",
    BriefSectionKind.IMMEDIATE_ATTENTION: "Immediate attention",
    BriefSectionKind.UPCOMING_COMMITMENTS: "Today / upcoming commitments",
    BriefSectionKind.RECENT_COMMUNICATIONS: "Recent communications / commitments",
    BriefSectionKind.PROJECT_CONTEXT: "Project / operational context",
    BriefSectionKind.RISKS_GAPS: "Risks, gaps and stale evidence",
    BriefSectionKind.SUGGESTED_ACTIONS: "Suggested internal actions or decisions",
}


@dataclass(frozen=True, slots=True)
class _RankedEvidence:
    evidence: ContextEvidence
    freshness: FreshnessState
    score: int
    reasons: tuple[str, ...]
    section: BriefSectionKind


@dataclass(frozen=True, slots=True)
class DailyIntelligenceComposer:
    """Build a typed owner brief from already-authorised bounded evidence."""

    maximum_priorities: int = 10
    policies: tuple[SourceBriefPolicy, ...] = DEFAULT_SOURCE_POLICIES
    expected_capabilities: tuple[str, ...] = (
        "calendar.search",
        "outlook.search",
        "local-files.search",
    )

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_priorities <= 10:
            raise ValueError("maximum priorities must be between zero and ten")
        if len({item.capability_id for item in self.policies}) != len(self.policies):
            raise ValueError("source policies must have unique capability IDs")

    def compose(
        self, context: AssembledContext, *, now: datetime
    ) -> DailyIntelligenceBrief:
        if now.tzinfo is None:
            raise ValueError("brief generation time must be timezone-aware")
        policy_by_capability = {item.capability_id: item for item in self.policies}
        corroboration = _corroboration_counts(context.evidence)
        ranked = tuple(
            sorted(
                (
                    self._rank(
                        item,
                        now=now,
                        policy=policy_by_capability.get(item.capability_id),
                        corroborating_sources=corroboration[_corroboration_key(item)],
                    )
                    for item in context.evidence
                ),
                key=lambda item: (-item.score, item.evidence.context_id),
            )
        )
        section_items: dict[BriefSectionKind, list[DailyBriefItem]] = {
            kind: [] for kind in BriefSectionKind
        }
        self._add_summary(section_items, ranked)
        for index, item in enumerate(ranked[: self.maximum_priorities], start=1):
            fact = _fact_item(item, index)
            section_items[item.section].append(fact)
            if item.freshness in {FreshnessState.STALE, FreshnessState.UNKNOWN}:
                section_items[BriefSectionKind.RISKS_GAPS].append(
                    _stale_item(item, index)
                )
        for index, item in enumerate(
            (
                value
                for value in ranked
                if value.freshness in {FreshnessState.CURRENT, FreshnessState.AGEING}
            ),
            start=1,
        ):
            if index > 3:
                break
            section_items[BriefSectionKind.IMMEDIATE_ATTENTION].append(
                _attention_item(item, index)
            )
            section_items[BriefSectionKind.SUGGESTED_ACTIONS].append(
                _action_item(item, index)
            )
        self._add_gaps(section_items, context, ranked)
        sections = tuple(
            DailyBriefSection(kind, _SECTION_TITLES[kind], tuple(section_items[kind]))
            for kind in BriefSectionKind
        )
        return DailyIntelligenceBrief(now, sections)

    def priorities(
        self, brief: DailyIntelligenceBrief
    ) -> tuple[IntelligencePriority, ...]:
        evidence_items = tuple(
            item
            for item in brief.items
            if item.kind is StatementKind.FACT
            and item.section
            not in {BriefSectionKind.RISKS_GAPS, BriefSectionKind.EXECUTIVE_SUMMARY}
        )[: self.maximum_priorities]
        return tuple(
            IntelligencePriority(
                item.title,
                item.text,
                item.evidence_ids,
                item.freshness.value,
                "evidence-backed",
                "Review the cited evidence and confirm the owner and next decision.",
                (
                    "Current status, accountable owner, and required decision are "
                    "not established by this evidence alone.",
                ),
            )
            for item in evidence_items
        )

    def _rank(
        self,
        item: ContextEvidence,
        *,
        now: datetime,
        policy: SourceBriefPolicy | None,
        corroborating_sources: int,
    ) -> _RankedEvidence:
        freshness = _freshness(item, policy, now)
        freshness_points = {
            FreshnessState.CURRENT: 5,
            FreshnessState.AGEING: 3,
            FreshnessState.STALE: 0,
            FreshnessState.UNKNOWN: 0,
        }[freshness]
        if policy is None:
            decision_usefulness = recurrence = evidence_quality = 1
            section = BriefSectionKind.PROJECT_CONTEXT
        else:
            decision_usefulness = policy.decision_usefulness
            recurrence = policy.recurrence
            evidence_quality = policy.evidence_quality
            section = policy.section
        corroboration_points = min(max(corroborating_sources - 1, 0), 3)
        score = (
            freshness_points * 5
            + decision_usefulness * 4
            + corroboration_points * 3
            + recurrence * 2
            + evidence_quality * 2
        )
        reasons = (
            f"freshness={freshness.value}:{freshness_points}",
            f"decision_usefulness={decision_usefulness}",
            f"corroborating_source_families={corroborating_sources}",
            f"recurrence={recurrence}",
            f"provenance_confidence={evidence_quality}",
        )
        return _RankedEvidence(item, freshness, score, reasons, section)

    def _add_summary(
        self,
        sections: dict[BriefSectionKind, list[DailyBriefItem]],
        ranked: tuple[_RankedEvidence, ...],
    ) -> None:
        if not ranked:
            sections[BriefSectionKind.EXECUTIVE_SUMMARY].append(
                DailyBriefItem(
                    "summary:no-evidence",
                    BriefSectionKind.EXECUTIVE_SUMMARY,
                    StatementKind.UNKNOWN,
                    "No current brief can be established",
                    "No authorised evidence was available; this is a gap, not a "
                    "finding that nothing requires attention.",
                    (),
                    FreshnessState.UNKNOWN,
                    0,
                    ("no_authorised_evidence",),
                )
            )
            return
        counts = {state: 0 for state in FreshnessState}
        for item in ranked:
            counts[item.freshness] += 1
        sections[BriefSectionKind.EXECUTIVE_SUMMARY].append(
            DailyBriefItem(
                "summary:evidence",
                BriefSectionKind.EXECUTIVE_SUMMARY,
                StatementKind.INFERENCE,
                "Authorised evidence overview",
                f"{len(ranked)} bounded evidence item(s): "
                f"{counts[FreshnessState.CURRENT]} current, "
                f"{counts[FreshnessState.AGEING]} ageing, "
                f"{counts[FreshnessState.STALE]} stale, and "
                f"{counts[FreshnessState.UNKNOWN]} with unknown freshness.",
                tuple(item.evidence.context_id for item in ranked),
                FreshnessState.UNKNOWN,
                ranked[0].score,
                ("deterministic_evidence_count_summary",),
            )
        )

    def _add_gaps(
        self,
        sections: dict[BriefSectionKind, list[DailyBriefItem]],
        context: AssembledContext,
        ranked: tuple[_RankedEvidence, ...],
    ) -> None:
        present = {item.evidence.capability_id for item in ranked}
        unavailable_ids = {
            item.partition(":")[0] for item in context.unavailable_capabilities
        }
        for capability_id in self.expected_capabilities:
            if capability_id in present:
                continue
            reason = (
                "source unavailable under current capability or authority state"
                if capability_id in unavailable_ids
                else "no admitted evidence was returned by this source"
            )
            sections[BriefSectionKind.RISKS_GAPS].append(
                DailyBriefItem(
                    f"gap:{capability_id}",
                    BriefSectionKind.RISKS_GAPS,
                    StatementKind.UNKNOWN,
                    f"Gap: {capability_id}",
                    f"{capability_id} has {reason}; completeness is unknown.",
                    (),
                    FreshnessState.UNKNOWN,
                    0,
                    (reason.replace(" ", "_"),),
                )
            )
        for gap in context.unavailable_capabilities:
            capability_id = gap.partition(":")[0]
            if capability_id in self.expected_capabilities:
                continue
            sections[BriefSectionKind.RISKS_GAPS].append(
                DailyBriefItem(
                    f"gap:{gap}",
                    BriefSectionKind.RISKS_GAPS,
                    StatementKind.UNKNOWN,
                    f"Capability gap: {capability_id}",
                    f"{gap}; completeness is unknown.",
                    (),
                    FreshnessState.UNKNOWN,
                    0,
                    ("capability_unavailable",),
                )
            )


def _freshness(
    item: ContextEvidence, policy: SourceBriefPolicy | None, now: datetime
) -> FreshnessState:
    if item.source_timestamp is None or policy is None:
        return FreshnessState.UNKNOWN
    age = now - item.source_timestamp.astimezone(now.tzinfo)
    if age <= policy.current_for:
        return FreshnessState.CURRENT
    if age <= policy.stale_after:
        return FreshnessState.AGEING
    return FreshnessState.STALE


def _corroboration_key(item: ContextEvidence) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", item.title.casefold()).strip()
    return normalized or item.context_id


def _corroboration_counts(
    evidence: tuple[ContextEvidence, ...],
) -> dict[str, int]:
    families: dict[str, set[str]] = {}
    for item in evidence:
        families.setdefault(_corroboration_key(item), set()).add(item.source_label)
    return {key: len(value) for key, value in families.items()}


def _fact_item(item: _RankedEvidence, index: int) -> DailyBriefItem:
    evidence = item.evidence
    return DailyBriefItem(
        f"evidence:{index}:{evidence.context_id}",
        item.section,
        StatementKind.FACT,
        evidence.title,
        evidence.excerpt,
        (evidence.context_id,),
        item.freshness,
        item.score,
        item.reasons,
    )


def _stale_item(item: _RankedEvidence, index: int) -> DailyBriefItem:
    evidence = item.evidence
    label = (
        "Stale evidence"
        if item.freshness is FreshnessState.STALE
        else "Unknown freshness"
    )
    return DailyBriefItem(
        f"freshness-risk:{index}:{evidence.context_id}",
        BriefSectionKind.RISKS_GAPS,
        StatementKind.INFERENCE,
        f"{label}: {evidence.title}",
        "This evidence cannot establish current business state without refreshed "
        "or timestamped source evidence.",
        (evidence.context_id,),
        item.freshness,
        item.score,
        item.reasons,
    )


def _attention_item(item: _RankedEvidence, index: int) -> DailyBriefItem:
    evidence = item.evidence
    return DailyBriefItem(
        f"attention:{index}:{evidence.context_id}",
        BriefSectionKind.IMMEDIATE_ATTENTION,
        StatementKind.RECOMMENDATION,
        evidence.title,
        "Review this evidence first and confirm the accountable owner, decision, "
        "and current status.",
        (evidence.context_id,),
        item.freshness,
        item.score,
        item.reasons,
        True,
    )


def _action_item(item: _RankedEvidence, index: int) -> DailyBriefItem:
    evidence = item.evidence
    return DailyBriefItem(
        f"suggested-action:{index}:{evidence.context_id}",
        BriefSectionKind.SUGGESTED_ACTIONS,
        StatementKind.PROPOSED_ACTION,
        f"Confirm next decision for {evidence.title}",
        "Prepare an internal owner-reviewed decision note from the cited evidence; "
        "do not send, mutate a source, or execute an external action.",
        (evidence.context_id,),
        item.freshness,
        item.score,
        item.reasons,
        True,
    )
