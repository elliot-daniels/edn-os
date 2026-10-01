"""Read projections and calendar boundaries tested through existing connectors."""

import urllib.error
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from tests.connectors.microsoft_calendar import test_calendar as calendar
from tests.connectors.microsoft_outlook import test_outlook as outlook
from tests.connectors.microsoft_sharepoint import test_sharepoint as sharepoint

from edn.connectors.errors import SourceUnavailableError
from edn.connectors.microsoft_calendar import CalendarWindow, MicrosoftCalendarConnector
from edn.connectors.microsoft_calendar.connector import _graph_datetime
from edn.connectors.microsoft_outlook import MicrosoftOutlookConnector
from edn.connectors.microsoft_sharepoint import MicrosoftSharePointConnector
from edn.intelligence import IntelligenceRequest
from edn.intelligence.morning_sources import (
    BusinessProjection,
    BusinessSourceAdapter,
    CalendarSourceAdapter,
    OutlookSourceAdapter,
    _due_date,
)


def intelligence_request(request):
    return IntelligenceRequest(
        "morning",
        request.principal,
        request.purpose,
        request.security_domain,
        request.classification,
    )


@pytest.mark.parametrize("local", ["2026-04-05T02:30:00", "2026-10-04T02:30:00"])
def test_calendar_rejects_fold_and_nonexistent_local_time(local):
    with pytest.raises(ValueError, match="ambiguous or nonexistent"):
        _graph_datetime({"dateTime": local, "timeZone": "Australia/Sydney"}, "UTC")


def test_calendar_explicit_offset_resolves_fold():
    result = _graph_datetime({"dateTime": "2026-04-05T02:30:00+11:00"}, "UTC")
    assert result.astimezone(UTC) == datetime(2026, 4, 4, 15, 30, tzinfo=UTC)


def test_calendar_bad_boundary_keeps_good_event_and_prefilter_coverage():
    bad = calendar._raw_event("bad")
    del bad["end"]
    connector = MicrosoftCalendarConnector(
        calendar._config(), calendar.FakeGraphClient((calendar._raw_event("good"), bad))
    )
    request = calendar._request(connector)
    adapter = CalendarSourceAdapter(connector, CalendarWindow.THIS_WEEK)
    batch = adapter.retrieve(
        intelligence_request(request),
        limit=10,
        now=calendar.NOW,
        authority=request.authority,
    )
    assert len(batch.evidence) == 1
    assert batch.pre_filter_count == 2
    assert batch.reasons == ("invalid_or_ambiguous_event",)
    assert batch.evidence[0].source_instance_id == adapter.source_instance_id


def test_calendar_all_day_across_dst_is_calendar_day_not_24_hours():
    event = calendar._raw_event()
    event.update(
        isAllDay=True,
        start={"dateTime": "2026-10-04T00:00:00", "timeZone": "Australia/Sydney"},
        end={"dateTime": "2026-10-05T00:00:00", "timeZone": "Australia/Sydney"},
    )
    connector = MicrosoftCalendarConnector(
        replace(calendar._config(), timezone_name="Australia/Sydney"),
        calendar.FakeGraphClient((event,)),
    )
    request = calendar._request(connector)
    batch = CalendarSourceAdapter(connector, CalendarWindow.THIS_WEEK).retrieve(
        intelligence_request(request),
        limit=10,
        now=datetime(2026, 10, 3, 20, tzinfo=UTC),
        authority=request.authority,
    )
    item = batch.evidence[0]
    assert "all day" in item.excerpt
    assert (
        item.temporal_end.astimezone(UTC) - item.temporal_start.astimezone(UTC)
    ).total_seconds() == 23 * 3600


@pytest.mark.parametrize(
    "due,expected",
    [("2026-09-16", "2026-09-16"), ("2026-09-15T23:30:00Z", "2026-09-16")],
)
def test_business_deadline_uses_configured_local_date(due, expected):
    assert _due_date(due, "Australia/Sydney").isoformat() == expected


def test_business_naive_deadline_is_not_guessed():
    with pytest.raises(ValueError):
        _due_date("2026-09-16T08:00:00", "Australia/Sydney")


def test_business_minimum_projection_filters_before_coverage_and_preserves_provenance():
    config = replace(
        sharepoint._config(),
        allowed_fields=(
            "Title",
            "Status",
            "Due",
            "Project",
            "IMSInformationClassification",
        ),
    )
    raw = sharepoint._item("action1")
    raw["fields"].update(Status="Open", Due="2026-09-16", Project="4")
    connector = MicrosoftSharePointConnector(
        config,
        sharepoint.FakeSharePointClient(
            (raw, sharepoint._item("excluded", security="Other domain"))
        ),
    )
    request = sharepoint._request(connector)
    adapter = BusinessSourceAdapter(
        connector,
        BusinessProjection("action", "Status", "Due", "Project"),
        "open actions",
    )
    batch = adapter.retrieve(
        intelligence_request(request),
        limit=10,
        now=sharepoint.NOW,
        authority=request.authority,
    )
    assert batch.pre_filter_count == 2
    assert len(batch.evidence) == 1
    item = batch.evidence[0]
    assert item.business_facts.status == "open"
    assert item.business_facts.project_id == "4"
    assert item.source_timestamp == datetime(2026, 8, 11, 10, tzinfo=UTC)
    assert item.provenance[0].record.source_record_key == "action1"
    assert "UnapprovedField" not in item.excerpt
    assert "IMSDescription" not in item.excerpt


def test_business_projection_rejects_unapproved_field_before_read():
    client = sharepoint.FakeSharePointClient()
    connector = MicrosoftSharePointConnector(sharepoint._config(), client)
    with pytest.raises(ValueError, match="explicitly allowed"):
        BusinessSourceAdapter(
            connector, BusinessProjection("action", due="Secret"), "open"
        )
    assert client.calls == 0


@pytest.mark.parametrize("kind", ["calendar", "outlook"])
@pytest.mark.parametrize(
    "error", [TimeoutError(), urllib.error.URLError("private host")]
)
def test_real_http_clients_classify_transport_failure_without_network(kind, error):
    from edn.connectors.microsoft_calendar.client import MicrosoftGraphCalendarClient
    from edn.connectors.microsoft_outlook.client import MicrosoftGraphOutlookClient

    def failing_opener(*args, **kwargs):
        raise error

    client_type = (
        MicrosoftGraphCalendarClient
        if kind == "calendar"
        else MicrosoftGraphOutlookClient
    )
    client = client_type(outlook._Token(), opener=failing_opener)
    with pytest.raises(SourceUnavailableError, match="failed safely") as raised:
        client._get("https://graph.microsoft.com/v1.0/me")
    assert "private host" not in str(raised.value)


def test_outlook_empty_live_result_preserves_checked_coverage():
    connector = MicrosoftOutlookConnector(
        outlook._config(), outlook.FakeOutlookClient()
    )
    request = outlook._request(connector)
    batch = OutlookSourceAdapter(connector).retrieve(
        intelligence_request(request),
        limit=10,
        now=outlook.NOW,
        authority=request.authority,
    )
    assert batch.evidence == ()
    assert batch.pre_filter_count == 0
    assert batch.freshness == "checked"
