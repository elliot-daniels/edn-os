"""Adapters that preserve existing retrieval implementations behind Core contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from edn.connectors import ConnectorRequest
from edn.connectors.local_files import LocalFilesConnector
from edn.connectors.microsoft_calendar import CalendarWindow, MicrosoftCalendarConnector
from edn.connectors.microsoft_outlook import MailWindow, MicrosoftOutlookConnector
from edn.core import CapabilityUseDecision, EvidenceRef, SourceRef, UniversalRecordRef
from edn.intelligence.models import ContextEvidence, IntelligenceRequest
from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.retrieval import RetrievalEngine


class SourceAdapter(Protocol):
    capability_id: str
    operation: str
    resource_scope: tuple[str, ...]

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]: ...


@dataclass(slots=True)
class CapabilityGapAdapter:
    """Registry-visible source whose retrieval must never run while unavailable."""

    capability_id: str
    operation: str
    resource_scope: tuple[str, ...]

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]:
        del request, limit, now, authority
        raise RuntimeError("unavailable capability was invoked")


def _email_ref(
    request: IntelligenceRequest, source_key: str, evidence_id: str
) -> EvidenceRef:
    source = SourceRef("email-memory", "memory", "local-email", "EDN email memory")
    record = UniversalRecordRef(
        source,
        source_key,
        request.security_domain,
        request.classification,
        "email",
        source_uri=f"edn-email:{source_key}",
    )
    return EvidenceRef(evidence_id, record, locator="retrieved email excerpt")


@dataclass(slots=True)
class EmailRetrievalAdapter:
    engine: RetrievalEngine
    capability_id: str = "email.retrieve"
    operation: str = "evidence.retrieve"
    resource_scope: tuple[str, ...] = ()

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]:
        del now, authority
        evidence = self.engine.retrieve(request.query, limit=limit)
        return tuple(
            ContextEvidence(
                context_id=f"email:{item.evidence_id}",
                capability_id=self.capability_id,
                source_label="Email memory",
                title=item.subject or "Email",
                excerpt=item.body_excerpt,
                score=float(limit - index),
                provenance=(
                    _email_ref(
                        request,
                        item.source_record_key,
                        f"email-{item.evidence_id}",
                    ),
                ),
            )
            for index, item in enumerate(evidence)
        )


@dataclass(slots=True)
class KnowledgeGraphAdapter:
    store: KnowledgeGraphStore
    capability_id: str = "knowledge.retrieve"
    operation: str = "evidence.retrieve"
    resource_scope: tuple[str, ...] = ()

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]:
        del now, authority
        entities = self.store.lookup_entities(request.query, limit=limit)
        items: list[ContextEvidence] = []
        for entity in entities:
            details = self.store.entity_details(entity.entity_id)
            if details is None or not details.source_record_keys:
                continue
            refs = tuple(
                _email_ref(request, key, f"kg-{entity.entity_id}-{index}")
                for index, key in enumerate(details.source_record_keys[:10], start=1)
            )
            relationships = ", ".join(
                f"{item.predicate} {item.entity.canonical_name}"
                for item in details.related_entities[:5]
            )
            excerpt = (
                f"{entity.entity_type.value}: {entity.canonical_name}; "
                f"supported by {entity.source_count} email(s)"
            )
            if relationships:
                excerpt += f"; related: {relationships}"
            items.append(
                ContextEvidence(
                    context_id=f"knowledge:{entity.entity_id}",
                    capability_id=self.capability_id,
                    source_label="Knowledge graph",
                    title=entity.canonical_name,
                    excerpt=excerpt,
                    score=float(entity.source_count),
                    provenance=refs,
                )
            )
        return tuple(items)


@dataclass(slots=True)
class LocalFilesEvidenceAdapter:
    connector: LocalFilesConnector
    resource_scope: tuple[str, ...]
    capability_id: str = "local-files.search"
    operation: str = "search"

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]:
        del now
        connector_request = ConnectorRequest(
            authority.request.request_id,
            authority.request.request_id,
            request.principal,
            request.purpose,
            request.security_domain,
            request.classification,
            self.capability_id,
            self.operation,
            authority,
            self.resource_scope,
        )
        terms = tuple(
            term.casefold() for term in request.query.split() if len(term) > 2
        )
        hits = []
        for resource_id in self.resource_scope:
            candidate, content = self.connector.extracted_content(
                connector_request, resource_id
            )
            folded = content.casefold()
            score = float(sum(folded.count(term) for term in terms))
            if terms and score == 0:
                continue
            excerpt = " ".join(content.split())[:500]
            evidence = self.connector.evidence((resource_id,))
            if evidence:
                hits.append(
                    ContextEvidence(
                        f"local-file:{resource_id}",
                        self.capability_id,
                        "Local document",
                        candidate.filename,
                        excerpt,
                        score,
                        evidence,
                    )
                )
        return tuple(
            sorted(hits, key=lambda item: (-item.score, item.context_id))[:limit]
        )


@dataclass(slots=True)
class OutlookEvidenceAdapter:
    connector: MicrosoftOutlookConnector
    window: MailWindow = MailWindow.LAST_7_DAYS
    capability_id: str = "outlook.search"
    operation: str = "search"

    @property
    def resource_scope(self) -> tuple[str, ...]:
        return (
            self.connector.config.mailbox_id,
            *self.connector.config.folder_ids,
            f"window:{self.window.value}",
        )

    def retrieve(
        self,
        request: IntelligenceRequest,
        *,
        limit: int,
        now: datetime,
        authority: CapabilityUseDecision,
    ) -> tuple[ContextEvidence, ...]:
        connector_request = ConnectorRequest(
            authority.request.request_id,
            authority.request.request_id,
            request.principal,
            request.purpose,
            request.security_domain,
            request.classification,
            self.capability_id,
            self.operation,
            authority,
            self.resource_scope,
        )
        result = self.connector.search_messages(
            connector_request, window=self.window, now=now, limit=limit
        )
        return tuple(
            ContextEvidence(
                f"outlook:{item.message_id}",
                self.capability_id,
                "Current Outlook mail",
                item.subject,
                f"{item.subject}; from {item.sender}; "
                f"received {item.received_at.isoformat()}; "
                f"importance {item.importance}; read {item.is_read}",
                float(limit - index),
                (self.connector.evidence_ref(item),),
            )
            for index, item in enumerate(result.messages)
        )


@dataclass(slots=True)
class CalendarEvidenceAdapter:
    connector: MicrosoftCalendarConnector
    window: CalendarWindow = CalendarWindow.THIS_WEEK
    capability_id: str = "calendar.search"
    operation: str = "search"

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
    ) -> tuple[ContextEvidence, ...]:
        connector_request = ConnectorRequest(
            authority.request.request_id,
            authority.request.request_id,
            request.principal,
            request.purpose,
            request.security_domain,
            request.classification,
            self.capability_id,
            self.operation,
            authority,
            self.resource_scope,
        )
        result = self.connector.search_events(
            connector_request, window=self.window, now=now, limit=limit
        )
        return tuple(
            ContextEvidence(
                f"calendar:{item.event_id}",
                self.capability_id,
                "Calendar",
                item.subject,
                _calendar_excerpt(item.subject, item.start, item.end, item.location),
                float(limit - index),
                (self.connector.evidence_ref(item),),
            )
            for index, item in enumerate(result.events)
        )


def _calendar_excerpt(
    subject: str, start: datetime, end: datetime, location: str | None
) -> str:
    value = f"{subject}: {start.isoformat()} to {end.isoformat()}"
    if location:
        value += f" at {location}"
    return value
