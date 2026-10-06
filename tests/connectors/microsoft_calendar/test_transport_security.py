"""Synthetic transport tests: no authentication or network source access."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from edn.connectors.errors import SourceUnavailableError
from edn.connectors.microsoft_calendar.client import (
    MAX_RESPONSE_BYTES,
    MicrosoftGraphCalendarClient,
    _NoRedirectHandler,
)

START = datetime(2026, 10, 6, tzinfo=UTC)


class Token:
    def __init__(self) -> None:
        self.calls = 0

    def acquire_token(self) -> str:
        self.calls += 1
        return "synthetic-bearer"


def client_with_pages(*pages: Any):
    requests: list[urllib.request.Request] = []
    remaining = iter(pages)

    def opener(request, **kwargs):
        assert kwargs == {"timeout": 30}
        requests.append(request)
        return io.BytesIO(json.dumps(next(remaining)).encode())

    return MicrosoftGraphCalendarClient(Token(), opener=opener), requests


def view(client, **kwargs):
    options = {
        "calendar_id": "default",
        "start": START,
        "end": START + timedelta(days=7),
        "timezone_name": "Australia/Adelaide",
        "limit": 25,
    }
    options.update(kwargs)
    return client.calendar_view(**options)


@pytest.mark.parametrize(
    "url",
    [
        "http://graph.microsoft.com/v1.0/me/calendars",
        "https://graph.microsoft.com.evil.example/v1.0/me/calendars",
        "https://user@graph.microsoft.com/v1.0/me/calendars",
        "https://graph.microsoft.com:443/v1.0/me/calendars",
        "https://graph.microsoft.com/v1.0/me/calendars#fragment",
        "https://graph.microsoft.com\n/v1.0/me/calendars",
    ],
)
def test_origin_rejected_before_authentication_or_transport(url):
    token = Token()
    client = MicrosoftGraphCalendarClient(token, opener=lambda *_a, **_k: pytest.fail())
    with pytest.raises(ValueError, match="origin"):
        client._get(url)
    assert token.calls == 0


def test_redirect_rejected_and_bearer_is_not_redirectable():
    client, requests = client_with_pages({"value": []})
    view(client)
    request = requests[0]
    assert "Authorization" not in request.headers
    assert request.unredirected_hdrs["Authorization"] == "Bearer synthetic-bearer"
    with pytest.raises(urllib.error.URLError, match="redirects"):
        _NoRedirectHandler().redirect_request(
            request, None, 302, "Found", {}, "https://evil.example/"
        )
    copied = urllib.request.HTTPRedirectHandler().redirect_request(
        request, None, 302, "Found", {}, "https://evil.example/"
    )
    assert copied is not None
    assert not copied.has_header("Authorization")


def test_default_opener_uses_redirect_rejecting_handler(monkeypatch):
    import edn.connectors.microsoft_calendar.client as module

    handlers = []

    class Opener:
        def open(self, request, **kwargs):
            assert request.get_method() == "GET"
            return io.BytesIO(b'{"value": []}')

    def build(handler):
        handlers.append(handler)
        return Opener()

    monkeypatch.setattr(module.urllib.request, "build_opener", build)
    view(MicrosoftGraphCalendarClient(Token()))
    assert isinstance(handlers[0], _NoRedirectHandler)


def test_event_query_is_exact_and_never_follows_even_hostile_continuation():
    client, requests = client_with_pages(
        {"value": [{"id": "one"}], "@odata.nextLink": "https://evil.example/body"}
    )
    assert view(client, calendar_id="synthetic/id?x") == ({"id": "one"},)
    assert len(requests) == 1
    parsed = urllib.parse.urlsplit(requests[0].full_url)
    assert parsed.path == "/v1.0/me/calendars/synthetic%2Fid%3Fx/calendarView"
    query = urllib.parse.parse_qs(parsed.query)
    assert query == {
        "startDateTime": [START.isoformat()],
        "endDateTime": [(START + timedelta(days=7)).isoformat()],
        "$top": ["25"],
        "$orderby": ["start/dateTime"],
        "$select": [MicrosoftGraphCalendarClient._EVENT_SELECT],
    }
    assert "body" not in query["$select"][0].split(",")


@pytest.mark.parametrize(
    "options",
    [
        {"start": START.replace(tzinfo=None)},
        {"end": START},
        {"end": START + timedelta(days=8)},
        {"limit": True},
        {"limit": 26},
        {"calendar_id": ".."},
        {"timezone_name": 'UTC"\r\nInjected: yes'},
    ],
)
def test_invalid_bounds_fail_before_read(options):
    client, requests = client_with_pages()
    with pytest.raises(ValueError):
        view(client, **options)
    assert requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"value": [{"id": str(i)} for i in range(26)]},
        {"value": [None]},
        {"value": {}},
    ],
)
def test_malformed_or_oversized_pages_fail_closed(payload):
    client, requests = client_with_pages(payload)
    with pytest.raises((SourceUnavailableError, RuntimeError)):
        view(client)
    assert len(requests) == 1


def test_byte_limit_uses_bounded_read():
    sizes = []

    class Response(io.BytesIO):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)

    client = MicrosoftGraphCalendarClient(
        Token(), opener=lambda *_a, **_k: Response(b"x" * (MAX_RESPONSE_BYTES + 1))
    )
    with pytest.raises(SourceUnavailableError, match="byte limit"):
        view(client)
    assert sizes == [MAX_RESPONSE_BYTES + 1]


def test_discovery_continuation_preserves_exact_resource_and_projection():
    first = "https://graph.microsoft.com/v1.0/me/calendars?" + urllib.parse.urlencode(
        {"$select": MicrosoftGraphCalendarClient._CALENDAR_SELECT, "$top": "25"}
    )
    client, requests = client_with_pages(
        {"value": [{"id": "one"}], "@odata.nextLink": first + "&%24skiptoken=opaque"},
        {"value": [{"id": "two"}]},
    )
    assert client.calendars() == ({"id": "one"}, {"id": "two"})
    assert len(requests) == 2


@pytest.mark.parametrize(
    "candidate",
    [
        "https://evil.example/v1.0/me/calendars?$skiptoken=x",
        "https://graph.microsoft.com/v1.0/users/other/calendars?$skiptoken=x",
        "https://graph.microsoft.com/v1.0/me/calendars?$select=body&$skiptoken=x",
        "https://graph.microsoft.com/v1.0/me/calendars?$select=id&$top=999&$skiptoken=x",
        123,
        "",
        "https://graph.microsoft.com/v1.0/me/calendars",
    ],
)
def test_untrusted_discovery_continuation_never_makes_second_read(candidate):
    client, requests = client_with_pages({"value": [], "@odata.nextLink": candidate})
    with pytest.raises(ValueError):
        client.calendars()
    assert len(requests) == 1


def test_discovery_duplicate_projection_or_cursor_is_rejected():
    base = "https://graph.microsoft.com/v1.0/me/calendars?" + urllib.parse.urlencode(
        {"$select": MicrosoftGraphCalendarClient._CALENDAR_SELECT, "$top": "25"}
    )
    for extra in (
        "&$skiptoken=x&$skiptoken=y",
        "&$select=body&$skiptoken=x",
        "&$expand=events&$skiptoken=x",
        "&$skiptoken=",
    ):
        client, requests = client_with_pages(
            {"value": [], "@odata.nextLink": base + extra}
        )
        with pytest.raises(ValueError, match="bounded query"):
            client.calendars()
        assert len(requests) == 1


def test_discovery_loop_stops_at_ten_pages():
    base = "https://graph.microsoft.com/v1.0/me/calendars?" + urllib.parse.urlencode(
        {"$select": MicrosoftGraphCalendarClient._CALENDAR_SELECT, "$top": "25"}
    )
    page = {"value": [], "@odata.nextLink": base + "&$skiptoken=opaque"}
    client, requests = client_with_pages(*[page] * 10)
    with pytest.raises(RuntimeError, match="safe bound"):
        client.calendars()
    assert len(requests) == 10
