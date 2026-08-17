from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from edn.connectors import ConnectorRequest, check_connector
from edn.connectors.microsoft_calendar import (
    CalendarConfig,
    CalendarEvent,
    CalendarScopeMode,
    CalendarWindow,
    MicrosoftCalendarConnector,
)
from edn.connectors.microsoft_calendar.cli import build_validation_report
from edn.connectors.microsoft_calendar.client import (
    BrowserInteractiveCredential,
    DeviceCodeCredential,
)
from edn.core import (
    AuthenticationStatus,
    CapabilityRegistry,
    CapabilityRuntimeState,
    CapabilityStatus,
    Classification,
    PermissionEvaluator,
    PermissionOutcome,
    PermissionRequest,
    PolicyRule,
    PolicySet,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    evaluate_capability_use,
)
from edn.intelligence import CalendarEvidenceAdapter, IntelligenceRequest

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
EDN = SecurityDomain("EDN", "EDN", tenant_id="tenant")
PERSONAL = SecurityDomain("PERSONAL", "Personal", tenant_id="tenant")
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)


class FakeGraphClient:
    def __init__(self, events: tuple[dict[str, Any], ...] = ()) -> None:
        self.events = events
        self.calls: list[tuple[datetime, datetime, str, int]] = []

    def calendars(self) -> tuple[dict[str, Any], ...]:
        return ({"id": "edn-calendar", "name": "EDN"},)

    def calendar_view(
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
        *,
        timezone_name: str,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        assert calendar_id == "edn-calendar"
        self.calls.append((start, end, timezone_name, limit))
        return self.events[:limit]


def _config(
    *, mode: CalendarScopeMode = CalendarScopeMode.DEDICATED_EDN
) -> CalendarConfig:
    return CalendarConfig(
        "tenant",
        "elliot@example.com",
        "edn-calendar",
        "EDN calendar",
        "Australia/Adelaide",
        EDN,
        CLASSIFICATION,
        mode,
        "EDN" if mode is CalendarScopeMode.CATEGORY_REQUIRED else None,
    )


def _raw_event(
    identifier: str = "event-one", *, categories: tuple[str, ...] = ("EDN",)
) -> dict[str, Any]:
    return {
        "id": identifier,
        "subject": "Project review",
        "start": {"dateTime": "2026-08-11T09:00:00", "timeZone": "Australia/Adelaide"},
        "end": {"dateTime": "2026-08-11T10:00:00", "timeZone": "Australia/Adelaide"},
        "organizer": {"emailAddress": {"address": "owner@example.com"}},
        "attendees": [
            {
                "emailAddress": {"name": "Engineer", "address": "e@example.com"},
                "status": {"response": "accepted"},
            }
        ],
        "location": {"displayName": "Adelaide"},
        "isAllDay": False,
        "recurrence": None,
        "webLink": "https://outlook.office.com/calendar/item/one",
        "lastModifiedDateTime": "2026-08-10T08:00:00Z",
        "categories": list(categories),
        "body": {"content": "must never be parsed"},
    }


def _request(
    connector: MicrosoftCalendarConnector,
    capability_id: str = "calendar.search",
    operation: str = "search",
    *,
    domain: SecurityDomain = EDN,
) -> ConnectorRequest:
    principal = PrincipalContext("elliot", "tenant", frozenset({domain}), True)
    purpose = Purpose("weekly-review", "Weekly intelligence")
    scope = ("edn-calendar", "window:this-week")
    permission_request = PermissionRequest(
        "calendar-policy-request",
        principal,
        purpose,
        capability_id,
        operation,
        domain,
        CLASSIFICATION,
        scope,
    )
    target = next(
        item
        for item in connector.manifest.capabilities
        if item.capability_id == capability_id
    )
    registry = CapabilityRegistry()
    registry.register(
        target,
        CapabilityRuntimeState(
            CapabilityStatus.READY, AuthenticationStatus.VALID, health="healthy"
        ),
    )
    policy = PermissionEvaluator(
        PolicySet(
            "calendar-test-policy",
            "1",
            (
                PolicyRule(
                    "allow-calendar-read",
                    PermissionOutcome.ALLOWED,
                    "Synthetic read-only authority.",
                    capability_ids=frozenset({capability_id}),
                    operations=frozenset({operation}),
                    domain_ids=frozenset({domain.domain_id}),
                ),
            ),
        )
    )
    decision = evaluate_capability_use(registry, policy, permission_request, now=NOW)
    return ConnectorRequest(
        "calendar-request",
        "calendar-correlation",
        principal,
        purpose,
        domain,
        CLASSIFICATION,
        capability_id,
        operation,
        decision,
        scope,
    )


def test_calendar_connector_conforms_and_has_no_write_capability() -> None:
    connector = MicrosoftCalendarConnector(_config(), FakeGraphClient())

    assert check_connector(connector).conforms
    assert connector.manifest.supported_operations == {"discover", "search", "verify"}
    assert "act" not in connector.manifest.supported_operations
    assert all(
        capability.required_permissions == {"Calendars.Read"}
        for capability in connector.manifest.capabilities
    )


def test_device_code_credential_allows_only_exact_pa005_scopes() -> None:
    credential = DeviceCodeCredential(
        "tenant", "client", ("User.Read", "Calendars.Read", "Mail.Read")
    )

    assert credential.scopes == ("User.Read", "Calendars.Read", "Mail.Read")
    with pytest.raises(ValueError, match="exceeds"):
        DeviceCodeCredential("tenant", "client", ("Calendars.ReadWrite",))
    with pytest.raises(ValueError, match="unique"):
        DeviceCodeCredential("tenant", "client", ("Mail.Read", "Mail.Read"))


def test_browser_pkce_credential_is_memory_only_and_identity_bound() -> None:
    calls: list[dict[str, Any]] = []

    class FakeApp:
        def acquire_token_interactive(self, **kwargs):
            calls.append(kwargs)
            return {
                "access_token": "synthetic-token",
                "scope": "User.Read Calendars.Read Mail.Read openid profile",
                "id_token_claims": {
                    "tid": "tenant",
                    "preferred_username": "owner@example.com",
                },
            }

    def factory(client_id, **kwargs):
        assert client_id == "client"
        assert kwargs["authority"].endswith("/tenant")
        assert kwargs["token_cache"].__class__.__name__ == "TokenCache"
        return FakeApp()

    credential = BrowserInteractiveCredential(
        "tenant",
        "client",
        "owner@example.com",
        ("User.Read", "Calendars.Read", "Mail.Read"),
        app_factory=factory,
    )

    assert credential.acquire_token() == "synthetic-token"
    assert credential.acquire_token() == "synthetic-token"
    assert len(calls) == 1
    assert calls[0]["prompt"] == "select_account"
    assert calls[0]["port"] == 8400
    assert calls[0]["scopes"] == [
        "https://graph.microsoft.com/User.Read",
        "https://graph.microsoft.com/Calendars.Read",
        "https://graph.microsoft.com/Mail.Read",
    ]


@pytest.mark.parametrize(
    ("claims", "scope"),
    [
        (
            {"tid": "other", "preferred_username": "owner@example.com"},
            "User.Read Calendars.Read Mail.Read",
        ),
        (
            {"tid": "tenant", "preferred_username": "other@example.com"},
            "User.Read Calendars.Read Mail.Read",
        ),
        (
            {"tid": "tenant", "preferred_username": "owner@example.com"},
            "Calendars.Read Mail.ReadWrite",
        ),
    ],
)
def test_browser_pkce_credential_rejects_identity_or_scope_drift(
    claims: dict[str, str], scope: str
) -> None:
    class FakeApp:
        def acquire_token_interactive(self, **_kwargs):
            return {
                "access_token": "synthetic-token",
                "scope": scope,
                "id_token_claims": claims,
            }

    credential = BrowserInteractiveCredential(
        "tenant",
        "client",
        "owner@example.com",
        ("User.Read", "Calendars.Read", "Mail.Read"),
        app_factory=lambda *_args, **_kwargs: FakeApp(),
    )

    with pytest.raises(PermissionError):
        credential.acquire_token()


@pytest.mark.parametrize(
    ("window", "expected_days"),
    [
        (CalendarWindow.TODAY, 1),
        (CalendarWindow.NEXT_7_DAYS, 7),
        (CalendarWindow.THIS_WEEK, 7),
        (CalendarWindow.LAST_7_DAYS, 7),
    ],
)
def test_time_windows_are_bounded_and_adelaide_aware(
    window: CalendarWindow, expected_days: int
) -> None:
    start, end = window.bounds(NOW, "Australia/Adelaide")

    assert start.tzinfo is not None
    assert end - start <= (end - start).__class__(days=expected_days)
    assert start.utcoffset() is not None


def test_search_excludes_body_and_preserves_serializable_provenance() -> None:
    connector = MicrosoftCalendarConnector(_config(), FakeGraphClient((_raw_event(),)))

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=5
    )

    assert result.pre_filter_count == 1
    assert result.admitted_count == 1
    assert result.rejected_count == 0
    assert "must never" not in result.events[0].to_json()
    assert CalendarEvent.from_dict(result.events[0].to_dict()) == result.events[0]
    evidence = connector.evidence_ref(result.events[0])
    assert evidence.record.security_domain == EDN
    assert evidence.record.classification == CLASSIFICATION


def test_category_mode_fails_closed_for_mixed_calendar() -> None:
    client = FakeGraphClient(
        (
            _raw_event("business", categories=("EDN",)),
            _raw_event("personal", categories=()),
        )
    )
    connector = MicrosoftCalendarConnector(
        _config(mode=CalendarScopeMode.CATEGORY_REQUIRED), client
    )

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=5
    )

    assert result.pre_filter_count == 2
    assert result.admitted_count == 1
    assert result.rejected_count == 1
    assert result.rejection_reasons_dict() == {"category_not_admitted": 1}
    assert tuple(item.event_id for item in result.events) == ("business",)


def test_five_graph_events_two_exact_edn_reports_counts_and_two_evidence() -> None:
    raw = tuple(
        _raw_event(
            f"event-{index}",
            categories=("EDN",) if index in {1, 4} else ("Other",),
        )
        for index in range(5)
    )
    connector = MicrosoftCalendarConnector(
        _config(mode=CalendarScopeMode.CATEGORY_REQUIRED), FakeGraphClient(raw)
    )

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=25
    )
    evidence = tuple(connector.evidence_ref(item) for item in result.events)

    assert result.counts_dict() == {
        "pre_filter_count": 5,
        "admitted_count": 2,
        "rejected_count": 3,
    }
    assert result.rejection_reasons_dict() == {"category_not_admitted": 3}
    assert len(evidence) == 2
    assert tuple(item.record.source_record_key for item in evidence) == (
        "event-1",
        "event-4",
    )


def test_five_graph_events_zero_edn_retains_counts_without_content_leakage() -> None:
    raw = tuple(
        _raw_event(f"private-{index}", categories=("Personal",))
        | {"subject": f"REJECTED SECRET {index}"}
        for index in range(5)
    )
    connector = MicrosoftCalendarConnector(
        _config(mode=CalendarScopeMode.CATEGORY_REQUIRED), FakeGraphClient(raw)
    )

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=25
    )
    report = build_validation_report(
        result,
        account="elliot@example.com",
        calendar_id="edn-calendar",
        domain=EDN,
        classification=CLASSIFICATION,
        window="this-week",
    )

    assert result.pre_filter_count == 5
    assert result.admitted_count == 0
    assert result.rejected_count == 5
    assert result.events == ()
    assert report["events"] == []
    assert "REJECTED SECRET" not in str(report)


def test_all_graph_events_are_admitted_when_all_exact_edn() -> None:
    connector = MicrosoftCalendarConnector(
        _config(mode=CalendarScopeMode.CATEGORY_REQUIRED),
        FakeGraphClient(tuple(_raw_event(f"event-{index}") for index in range(5))),
    )

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=25
    )

    assert (result.pre_filter_count, result.admitted_count, result.rejected_count) == (
        5,
        5,
        0,
    )


def test_category_matching_is_case_sensitive_and_exact() -> None:
    raw = (
        _raw_event("exact", categories=("EDN",)),
        _raw_event("lower", categories=("edn",)),
        _raw_event("prefix", categories=("EDN Project",)),
        _raw_event("spaced", categories=(" EDN ",)),
    )
    connector = MicrosoftCalendarConnector(
        _config(mode=CalendarScopeMode.CATEGORY_REQUIRED), FakeGraphClient(raw)
    )

    result = connector.search_events(
        _request(connector), window=CalendarWindow.THIS_WEEK, now=NOW, limit=25
    )

    assert tuple(item.event_id for item in result.events) == ("exact",)
    assert result.counts_dict() == {
        "pre_filter_count": 4,
        "admitted_count": 1,
        "rejected_count": 3,
    }


def test_calendar_adapter_emits_source_neutral_evidence() -> None:
    connector = MicrosoftCalendarConnector(_config(), FakeGraphClient((_raw_event(),)))
    connector_request = _request(connector)
    adapter = CalendarEvidenceAdapter(connector)
    request = IntelligenceRequest(
        "What matters this week?",
        connector_request.principal,
        connector_request.purpose,
        connector_request.security_domain,
        connector_request.classification,
    )

    evidence = adapter.retrieve(
        request,
        limit=5,
        now=NOW,
        authority=connector_request.authority,
    )

    assert len(evidence) == 1
    assert evidence[0].source_label == "Calendar"
    assert evidence[0].provenance[0].record.record_type == "calendar.event"


def test_wrong_domain_cannot_form_authorized_request_or_reach_graph() -> None:
    client = FakeGraphClient((_raw_event(),))
    connector = MicrosoftCalendarConnector(_config(), client)

    with pytest.raises(ValueError, match="explicitly usable"):
        _request(connector, domain=PERSONAL)

    assert client.calls == []
