"""Deterministic, cited deadline rules over minimal admitted projections."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from edn.intelligence.models import (
    AssembledContext,
    BriefSectionKind,
    ContextEvidence,
    DailyBriefItem,
    FreshnessState,
    StatementKind,
)

OPEN_ACTION = frozenset({"open", "in progress", "not started", "blocked"})
ACTIVE_PROJECT = frozenset({"active", "in progress"})
CLOSED = frozenset(
    {"completed", "complete", "closed", "cancelled", "inactive", "archived"}
)


def business_items(
    context: AssembledContext,
    *,
    now: datetime,
    timezone: str,
) -> tuple[DailyBriefItem, ...]:
    today = now.astimezone(ZoneInfo(timezone)).date()
    records = [item for item in context.evidence if item.business_facts is not None]
    output: list[DailyBriefItem] = []

    def current(item: ContextEvidence) -> bool:
        coverage = next(
            (
                source
                for source in context.source_coverage
                if source.capability_id == item.capability_id
                and source.source_instance_id == item.source_instance_id
            ),
            None,
        )
        return (
            coverage is not None
            and coverage.checked_at is not None
            and coverage.freshness == "checked"
            and timedelta(0) <= now - coverage.checked_at <= timedelta(days=1)
        )

    def related(kind: str, identity: str) -> ContextEvidence | None:
        matches = [
            item
            for item in records
            if item.business_facts is not None
            and item.business_facts.kind == kind
            and item.business_facts.record_id == identity
        ]
        return matches[0] if len(matches) == 1 else None

    def gap(item: ContextEvidence, reason: str) -> None:
        output.append(
            DailyBriefItem(
                f"business-gap:{item.context_id}:{reason}",
                BriefSectionKind.RISKS_GAPS,
                StatementKind.UNKNOWN,
                f"Coverage needed: {item.title}",
                reason,
                (),
                FreshnessState.UNKNOWN,
                0,
                (reason,),
            )
        )

    for item in records:
        facts = item.business_facts
        assert facts is not None
        if facts.kind == "client" or facts.status in CLOSED:
            continue
        known_status = OPEN_ACTION if facts.kind == "action" else ACTIVE_PROJECT
        if facts.status not in known_status:
            gap(item, "status_unknown_no_urgency_inferred")
            continue
        coverage = next(
            (
                source
                for source in context.source_coverage
                if source.capability_id == item.capability_id
                and source.source_instance_id == item.source_instance_id
            ),
            None,
        )
        if (
            coverage is None
            or coverage.checked_at is None
            or coverage.freshness != "checked"
            or not timedelta(0) <= now - coverage.checked_at <= timedelta(days=1)
        ):
            gap(item, "current_business_state_unverified")
            continue
        references = [item.context_id]
        context_text = ""
        client_id = facts.client_id
        if facts.project_id:
            project = related("project", facts.project_id)
            if project is None:
                gap(item, "project_relationship_missing_or_conflicting")
                continue
            if not current(project):
                gap(item, "project_current_state_unverified")
                continue
            project_facts = project.business_facts
            assert project_facts is not None
            if project_facts.status in CLOSED:
                continue
            if project_facts.status not in ACTIVE_PROJECT:
                gap(item, "project_status_unknown")
                continue
            references.append(project.context_id)
            context_text = f" Project: {project.title}."
            client_id = client_id or project_facts.client_id
        if client_id:
            client = related("client", client_id)
            if client is None or not current(client):
                gap(item, "client_relationship_missing_or_conflicting")
            else:
                references.append(client.context_id)
                context_text += f" Client: {client.title}."
        if facts.due_date is None:
            if facts.kind == "action":
                gap(item, "action_deadline_not_established")
            continue
        days = (facts.due_date - today).days
        if days > 7:
            continue
        label = (
            "Overdue" if days < 0 else "Due today" if days == 0 else "Upcoming deadline"
        )
        section = (
            BriefSectionKind.IMMEDIATE_ATTENTION
            if days <= 0
            else BriefSectionKind.UPCOMING_COMMITMENTS
        )
        output.append(
            DailyBriefItem(
                f"business:{item.context_id}",
                section,
                StatementKind.FACT,
                f"{label}: {item.title}",
                f"Recorded status: {facts.status}; due {facts.due_date.isoformat()}."
                + context_text
                + (f" Owner: {facts.owner}." if facts.owner else ""),
                tuple(references),
                FreshnessState.CURRENT,
                120 if days < 0 else 110 if days == 0 else 100 - days,
                ("explicit_recorded_deadline", f"days_to_due={days}"),
            )
        )
    return tuple(sorted(output, key=lambda item: (-item.rank_score, item.item_id)))
