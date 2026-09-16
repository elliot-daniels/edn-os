"""Bounded morning sources. Clients and authority must be supplied by the host.

This module does not authenticate, discover sources, or grant permissions.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from edn.connectors import ConnectorRequest
from edn.connectors.errors import SourceUnavailableError
from edn.connectors.microsoft_calendar import CalendarWindow, MicrosoftCalendarConnector
from edn.connectors.microsoft_outlook import MailWindow, MicrosoftOutlookConnector
from edn.connectors.microsoft_sharepoint import MicrosoftSharePointConnector
from edn.core import CapabilityUseDecision
from edn.intelligence.adapters import EmailRetrievalAdapter
from edn.intelligence.models import (
    BusinessFacts,
    ContextEvidence,
    IntelligenceRequest,
    SourceBatch,
)
from edn.memory.storage import SQLiteEmailStore


def connector_request(
    request: IntelligenceRequest,
    authority: CapabilityUseDecision,
    capability: str,
    scope: tuple[str, ...],
) -> ConnectorRequest:
    return ConnectorRequest(
        authority.request.request_id,
        authority.request.request_id,
        request.principal,
        request.purpose,
        request.security_domain,
        request.classification,
        capability,
        "search",
        authority,
        scope,
    )


@dataclass(slots=True)
class EmailCorpusAdapter:
    adapter: EmailRetrievalAdapter
    store: SQLiteEmailStore
    source_instance_id: str
    capability_id: str = "email.retrieve"
    operation: str = "evidence.retrieve"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        return (self.source_instance_id,)

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> SourceBatch:
        evidence = self.adapter.retrieve(
            request, limit=limit, now=now, authority=authority
        )
        try:
            statuses = self.store.import_status()
        except (OSError, ValueError, sqlite3.Error) as error:
            raise SourceUnavailableError(
                "Email ingestion metadata unavailable"
            ) from error
        reasons = ["local_archive_not_live_inbox"]
        freshness = "unknown"
        if not statuses:
            reasons.append("ingestion_status_unknown")
        elif any(status != "completed" for status, _ in statuses):
            reasons.append("ingestion_incomplete")
        elif any(at.tzinfo is None or at > now for _, at in statuses):
            reasons.append("ingestion_timestamp_unknown")
        elif any(now - at > timedelta(days=1) for _, at in statuses):
            freshness = "stale"
            reasons.append("local_corpus_may_be_stale")
        else:
            freshness = "recent_import_snapshot"
            reasons.append("recent_import_does_not_prove_mailbox_coverage")
        if request.retrieval_mode == "recent":
            reasons.append(
                "recent_evidence_exists" if evidence else "no_evidence_in_period"
            )
        else:
            reasons.append(
                "matching_evidence_exists" if evidence else "no_matching_evidence"
            )
        items = tuple(
            replace(
                item,
                source_instance_id=self.source_instance_id,
                context_id=f"{self.source_instance_id}:{item.context_id}",
                provenance=tuple(
                    replace(
                        ref,
                        record=replace(
                            ref.record,
                            source=replace(
                                ref.record.source,
                                source_instance_id=self.source_instance_id,
                            ),
                        ),
                    )
                    for ref in item.provenance
                ),
            )
            for item in evidence
        )
        return SourceBatch(
            items, len(items), now, len(items) >= limit, tuple(reasons), freshness
        )


@dataclass(slots=True)
class CalendarSourceAdapter:
    connector: MicrosoftCalendarConnector
    window: CalendarWindow = CalendarWindow.NEXT_7_DAYS
    capability_id: str = "calendar.search"
    operation: str = "search"

    @property
    def source_instance_id(self) -> str:
        config = self.connector.config
        return f"{config.tenant_id}:{config.account_id}:{config.calendar_id}"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        return (self.connector.config.calendar_id, f"window:{self.window.value}")

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> SourceBatch:
        result = self.connector.search_events(
            connector_request(
                request, authority, self.capability_id, self.resource_scope
            ),
            window=self.window,
            now=now,
            limit=limit,
        )
        items = tuple(
            ContextEvidence(
                f"calendar:{self.source_instance_id}:{event.event_id}",
                self.capability_id,
                "Calendar",
                event.subject,
                f"{event.start.isoformat()} to {event.end.isoformat()}"
                + (" (all day)" if event.is_all_day else ""),
                float(limit - index),
                (self.connector.evidence_ref(event),),
                event.end,
                "calendar_event_end",
                temporal_start=event.start,
                temporal_end=event.end,
                source_instance_id=self.source_instance_id,
            )
            for index, event in enumerate(result.events)
        )
        return SourceBatch(
            items,
            result.pre_filter_count,
            now,
            result.pre_filter_count >= limit,
            tuple(reason for reason, _ in result.rejection_reasons),
            "checked",
        )


@dataclass(slots=True)
class OutlookSourceAdapter:
    connector: MicrosoftOutlookConnector
    window: MailWindow = MailWindow.LAST_7_DAYS
    capability_id: str = "outlook.search"
    operation: str = "search"

    @property
    def source_instance_id(self) -> str:
        config = self.connector.config
        return f"{config.tenant_id}:{config.account_id}:{config.mailbox_id}"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        config = self.connector.config
        return (
            config.mailbox_id,
            *(config.authority_folder_ids or config.folder_ids),
            f"window:{self.window.value}",
        )

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> SourceBatch:
        result = self.connector.search_messages(
            connector_request(
                request, authority, self.capability_id, self.resource_scope
            ),
            window=self.window,
            now=now,
            limit=limit,
        )
        items = tuple(
            ContextEvidence(
                f"outlook:{self.source_instance_id}:{item.message_id}",
                self.capability_id,
                "Current Outlook metadata",
                item.subject,
                f"From {item.sender}; received {item.received_at.isoformat()}; "
                f"importance {item.importance}; read {item.is_read}",
                float(limit - index),
                (self.connector.evidence_ref(item),),
                item.received_at,
                "mail_received_at",
                source_instance_id=self.source_instance_id,
            )
            for index, item in enumerate(result.messages)
        )
        return SourceBatch(
            items,
            result.pre_filter_count,
            now,
            result.pre_filter_count >= limit,
            (),
            "checked",
        )


@dataclass(frozen=True, slots=True)
class BusinessProjection:
    """Explicit internal field names, never inferred from live list contents."""

    kind: str
    status: str = ""
    due: str = ""
    project: str = ""
    client: str = ""
    owner: str = ""
    timezone: str = "Australia/Sydney"

    def __post_init__(self) -> None:
        if self.kind not in {"project", "client", "action"}:
            raise ValueError("unsupported business projection")
        ZoneInfo(self.timezone)


@dataclass(slots=True)
class BusinessSourceAdapter:
    connector: MicrosoftSharePointConnector
    projection: BusinessProjection
    query: str
    capability_id: str = "sharepoint.search"
    operation: str = "search"

    def __post_init__(self) -> None:
        fields = self.projection
        required = {
            field
            for field in (
                fields.status,
                fields.due,
                fields.project,
                fields.client,
                fields.owner,
            )
            if field
        }
        if not required <= set(self.connector.config.allowed_fields):
            raise ValueError("projection fields must be explicitly allowed")
        if not self.query.strip():
            raise ValueError("bounded source query must be configured")

    @property
    def source_instance_id(self) -> str:
        config = self.connector.config
        return f"{config.tenant_id}:{config.site_id}:{config.list_id}"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        return (self.connector.config.site_id, self.connector.config.list_id)

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> SourceBatch:
        result = self.connector.search_records(
            connector_request(
                request, authority, self.capability_id, self.resource_scope
            ),
            query=self.query,
            now=now,
            limit=limit,
        )
        items = []
        reasons: set[str] = set()
        projection = self.projection
        for record in result.records:
            if record.modified_at > now:
                reasons.add("future_source_timestamp")
                continue
            values = dict(record.fields)
            due = None
            raw_due = values.get(projection.due, "")
            if raw_due:
                try:
                    due = _due_date(raw_due, projection.timezone)
                except ValueError:
                    reasons.add("invalid_deadline")
            facts = BusinessFacts(
                projection.kind,
                record.item_id,
                values.get(projection.status, "").strip().casefold(),
                due,
                values.get(projection.project, ""),
                values.get(projection.client, ""),
                values.get(projection.owner, ""),
            )
            items.append(
                ContextEvidence(
                    f"sharepoint:{self.source_instance_id}:{record.item_id}",
                    self.capability_id,
                    f"Business OS {projection.kind}",
                    record.title,
                    "; ".join(f"{name}: {value}" for name, value in record.fields)[
                        :2000
                    ],
                    1.0,
                    (self.connector.evidence_ref(record),),
                    record.modified_at,
                    "sharepoint_modified_at",
                    source_instance_id=self.source_instance_id,
                    business_facts=facts,
                )
            )
        return SourceBatch(
            tuple(items),
            result.pre_filter_count,
            now,
            result.pre_filter_count >= limit,
            tuple(sorted(reasons)),
            "checked",
        )


def _due_date(value: str, timezone: str) -> date:
    if len(value) == 10:
        return date.fromisoformat(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("deadline timestamp requires timezone")
    return parsed.astimezone(ZoneInfo(timezone)).date()
