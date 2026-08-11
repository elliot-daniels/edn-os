"""Read-only Microsoft 365 Calendar Connector SDK implementation."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from edn.connectors import (
    ConnectorManifest,
    ConnectorRequest,
    DiscoveryResult,
    ResourceCandidate,
    SearchResult,
    VerificationResult,
    VerificationStatus,
    require_supported_operation,
)
from edn.connectors.microsoft_calendar.client import GraphCalendarClient
from edn.connectors.microsoft_calendar.models import (
    CalendarAttendee,
    CalendarConfig,
    CalendarEvent,
    CalendarRetrievalResult,
    CalendarScopeMode,
    CalendarWindow,
)
from edn.core import CapabilityManifest, EvidenceRef, SourceRef, UniversalRecordRef

CONNECTOR_ID = "microsoft-calendar"
CONNECTOR_VERSION = "0.1.0"
READ_PERMISSION = "Calendars.Read"


class MicrosoftCalendarConnector:
    def __init__(self, config: CalendarConfig, client: GraphCalendarClient) -> None:
        self.config = config
        self.client = client
        capabilities = tuple(
            CapabilityManifest(
                capability_id,
                "microsoft-graph",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                frozenset({operation}),
                frozenset({READ_PERMISSION}),
                frozenset({config.security_domain.domain_id}),
                "read",
            )
            for capability_id, operation in (
                ("calendar.discover", "discover"),
                ("calendar.read", "search"),
                ("calendar.search", "search"),
                ("calendar.verify", "verify"),
            )
        )
        self._manifest = ConnectorManifest(
            CONNECTOR_ID,
            CONNECTOR_VERSION,
            "Microsoft 365 Calendar",
            "microsoft-graph",
            "Bounded delegated read-only calendar discovery and retrieval.",
            "calendar",
            capabilities,
            frozenset({"discover", "search", "verify"}),
            "urn:edn:schema:microsoft-calendar-config:1",
            "1.0.0",
        )

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    def discover(self, request: ConnectorRequest) -> DiscoveryResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        resources = []
        for item in self.client.calendars():
            identifier = str(item.get("id", ""))
            if not self._is_configured_calendar(item):
                continue
            resources.append(
                ResourceCandidate(
                    _safe_id("calendar", identifier),
                    "calendar",
                    f"msgraph-calendar:{identifier}",
                    request.security_domain,
                    request.classification,
                    required_permissions=(READ_PERMISSION,),
                    warnings=("event-body-excluded",),
                )
            )
        return DiscoveryResult(
            request.request_id, tuple(resources), processed_resources=len(resources)
        )

    def search_events(
        self,
        request: ConnectorRequest,
        *,
        window: CalendarWindow,
        now: datetime,
        limit: int,
    ) -> CalendarRetrievalResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        if not 1 <= limit <= 25:
            raise ValueError("calendar retrieval limit must be between 1 and 25")
        start, end = window.bounds(now, self.config.timezone_name)
        raw = self.client.calendar_view(
            self.config.calendar_id,
            start,
            end,
            timezone_name=self.config.timezone_name,
            limit=limit,
        )
        events = []
        for item in raw:
            event = self._event(item)
            if event is None or event.end < start or event.start >= end:
                continue
            events.append(event)
        admitted = tuple(sorted(events, key=lambda item: (item.start, item.event_id)))
        return CalendarRetrievalResult(len(raw), admitted)

    def search(self, request: ConnectorRequest) -> SearchResult:
        result = self.search_events(
            request,
            window=_window_from_scope(request.scope),
            now=datetime.now(UTC),
            limit=25,
        )
        return SearchResult(
            request.request_id,
            tuple(self.evidence_ref(event) for event in result.events),
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        matches = tuple(
            item
            for item in self.client.calendars()
            if self._is_configured_calendar(item)
        )
        return VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED
            if len(matches) == 1
            else VerificationStatus.FAILED,
            "Exact configured calendar identity was checked read-only.",
            1,
            len(matches),
            ("event-body-excluded",),
        )

    def evidence_ref(self, event: CalendarEvent) -> EvidenceRef:
        source = SourceRef(
            "microsoft-calendar.edn",
            CONNECTOR_ID,
            self.config.calendar_id,
            self.config.calendar_name,
        )
        record = UniversalRecordRef(
            source,
            event.event_id,
            event.security_domain,
            event.classification,
            "calendar.event",
            event.web_url,
            event.last_modified_at.isoformat(),
        )
        digest = hashlib.sha256(
            f"{self.config.calendar_id}:{event.event_id}".encode()
        ).hexdigest()
        return EvidenceRef(
            f"calendar-{digest}",
            record,
            locator=f"{event.start.isoformat()} to {event.end.isoformat()}",
            transformation_id="calendar-metadata",
            transformation_version=CONNECTOR_VERSION,
        )

    def _validate_request(self, request: ConnectorRequest) -> None:
        if request.security_domain != self.config.security_domain:
            raise PermissionError("calendar domain does not match approved source")
        if request.classification != self.config.classification:
            raise PermissionError("calendar classification does not match source")
        if self.config.calendar_id not in request.scope:
            raise PermissionError("request is not bound to the configured calendar")

    def _event(self, item: dict[str, Any]) -> CalendarEvent | None:
        categories = tuple(str(value) for value in item.get("categories", []))
        if (
            self.config.scope_mode is CalendarScopeMode.CATEGORY_REQUIRED
            and self.config.required_category not in categories
        ):
            return None
        start = _graph_datetime(item.get("start"), self.config.timezone_name)
        end = _graph_datetime(item.get("end"), self.config.timezone_name)
        modified = datetime.fromisoformat(
            str(item["lastModifiedDateTime"]).replace("Z", "+00:00")
        )
        attendees = tuple(
            CalendarAttendee(
                str(value.get("emailAddress", {}).get("name", "")),
                str(value.get("emailAddress", {}).get("address", "")),
                str(value.get("status", {}).get("response", "none")),
            )
            for value in item.get("attendees", [])
        )
        recurrence = item.get("recurrence")
        location = item.get("location", {}).get("displayName")
        organizer = item.get("organizer", {}).get("emailAddress", {}).get("address", "")
        return CalendarEvent(
            str(item["id"]),
            self.config.calendar_id,
            str(item.get("subject") or "(Private event)"),
            start,
            end,
            self.config.timezone_name,
            str(organizer),
            attendees,
            None if not location else str(location),
            item.get("isAllDay") is True,
            None if recurrence is None else "recurring",
            None if item.get("webLink") is None else str(item["webLink"]),
            modified,
            categories,
            self.config.security_domain,
            self.config.classification,
        )

    def _is_configured_calendar(self, item: dict[str, Any]) -> bool:
        if self.config.calendar_id == "default":
            return item.get("isDefaultCalendar") is True
        return str(item.get("id", "")) == self.config.calendar_id


def _graph_datetime(value: object, fallback_timezone: str) -> datetime:
    if not isinstance(value, dict):
        raise ValueError("Graph event timestamp must be an object")
    parsed = datetime.fromisoformat(str(value["dateTime"]).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        timezone_name = str(value.get("timeZone") or fallback_timezone)
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed


def _safe_id(prefix: str, native_id: str) -> str:
    return f"{prefix}:{hashlib.sha256(native_id.encode()).hexdigest()}"


def _window_from_scope(scope: tuple[str, ...]) -> CalendarWindow:
    values = [
        item.removeprefix("window:") for item in scope if item.startswith("window:")
    ]
    return CalendarWindow(values[0]) if len(values) == 1 else CalendarWindow.THIS_WEEK
