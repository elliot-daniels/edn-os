"""Synthetic security boundaries: no sockets, live identity or business data."""

import io
import json
import urllib.request
from email.message import Message
from urllib.response import addinfourl

import pytest

from edn.connectors.errors import SourceUnavailableError
from edn.connectors.microsoft_outlook.client import MAX_RESPONSE_BYTES
from edn.operations.models import Event
from edn.operations.outlook import (
    MAX_PAGE_RECORDS,
    OperationsOutlookClient,
    ingest_mailbox,
)
from edn.operations.storage import EventStore
from tests.operations.test_outlook import END, MAILBOX, START, Response, Token, message


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "destination",
    [
        "https://untrusted.example.test/messages",
        "http://graph.microsoft.com/messages",
        "https://graph.microsoft.com:8443/messages",
    ],
)
def test_default_transport_rejects_redirect_before_second_request(
    monkeypatch, code, destination
):
    requests = []
    original = urllib.request.build_opener

    class SyntheticHTTPS(urllib.request.HTTPSHandler):
        def https_open(self, request):
            requests.append(request)
            headers = Message()
            headers["Location"] = destination
            response = addinfourl(io.BytesIO(b""), headers, request.full_url, code)
            response.msg = "Synthetic redirect"
            return response

    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        lambda *handlers: original(SyntheticHTTPS(), *handlers),
    )
    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,))
    with pytest.raises(SourceUnavailableError):
        client.page(MAILBOX, START, END)
    assert len(requests) == 1
    assert requests[0].get_header("Authorization") == "Bearer synthetic"


def test_injected_standard_redirect_handler_cannot_copy_bearer():
    requests = []

    class SyntheticHTTPS(urllib.request.HTTPSHandler):
        def https_open(self, request):
            requests.append(request)
            headers = Message()
            if len(requests) == 1:
                headers["Location"] = "https://untrusted.example.test/messages"
                code, content = 302, b""
            else:
                code, content = 200, b'{"value": []}'
            response = addinfourl(io.BytesIO(content), headers, request.full_url, code)
            response.msg = "Synthetic response"
            return response

    opener = urllib.request.build_opener(SyntheticHTTPS()).open
    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,), opener=opener)
    client.page(MAILBOX, START, END)
    assert len(requests) == 2
    assert requests[0].get_header("Authorization") == "Bearer synthetic"
    assert requests[1].get_header("Authorization") is None


def test_single_record_exceeding_byte_limit_never_persists(tmp_path):
    sizes = []

    class LargeResponse(Response):
        def read(self, size=-1):
            sizes.append(size)
            return super().read(size)

    record = message(body={"contentType": "text", "content": "x" * MAX_RESPONSE_BYTES})
    client = OperationsOutlookClient(
        Token(),
        mailboxes=(MAILBOX,),
        opener=lambda *a, **k: LargeResponse({"value": [record]}),
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    with pytest.raises(SourceUnavailableError, match="byte limit"):
        ingest_mailbox(client, store, MAILBOX, START, END)
    assert sizes == [MAX_RESPONSE_BYTES + 1]
    assert store.list_events() == ()


@pytest.mark.parametrize("count", [MAX_PAGE_RECORDS, MAX_PAGE_RECORDS + 1])
def test_small_response_record_limit_is_independent(tmp_path, count):
    payload = {"value": [message(str(index)) for index in range(count)]}
    assert len(json.dumps(payload).encode()) < MAX_RESPONSE_BYTES
    client = OperationsOutlookClient(
        Token(), mailboxes=(MAILBOX,), opener=lambda *a, **k: Response(payload)
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    if count > MAX_PAGE_RECORDS:
        with pytest.raises(ValueError, match="record limit"):
            ingest_mailbox(client, store, MAILBOX, START, END)
        assert store.list_events() == ()
    else:
        report = ingest_mailbox(client, store, MAILBOX, START, END)
        assert report.inserted == count and report.complete


@pytest.mark.parametrize(
    "attachments",
    [
        None,
        {},
        "bad",
        [None],
        ["bad"],
        [{}],
        [{"name": None}],
        [{"size": -1}],
        [{"size": True}],
        [{"size": "42"}],
        [{"isInline": "false"}],
        [{"contentBytes": "not-metadata"}],
    ],
)
def test_malformed_attachment_metadata_is_rejected_before_persistence(
    tmp_path, attachments
):
    client = OperationsOutlookClient(
        Token(),
        mailboxes=(MAILBOX,),
        opener=lambda *a, **k: Response({"value": [message(attachments=attachments)]}),
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    report = ingest_mailbox(client, store, MAILBOX, START, END)
    assert report.failed == 1 and report.inserted == 0 and not report.complete
    assert store.list_events() == ()


def test_mutated_event_metadata_revalidated_before_database_is_opened(tmp_path):
    metadata = {"name": "safe.pdf"}
    event = Event(
        "outlook", MAILBOX, "m1", START, "inbound", "email", attachments=(metadata,)
    )
    metadata["name"] = None
    path = tmp_path / "never-created.db"
    with pytest.raises(ValueError, match="metadata"):
        EventStore(path).insert(event)
    assert not path.exists()


@pytest.mark.parametrize("excess", [0, 1])
def test_byte_cap_boundary_with_zero_records(excess):
    content = b'{"value": []}'
    content += b" " * (MAX_RESPONSE_BYTES - len(content) + excess)

    class BoundedResponse(Response):
        def read(self, size=-1):
            assert size == MAX_RESPONSE_BYTES + 1
            return content[:size]

    client = OperationsOutlookClient(
        Token(),
        mailboxes=(MAILBOX,),
        opener=lambda *a, **k: BoundedResponse({}),
    )
    if excess:
        with pytest.raises(SourceUnavailableError, match="byte limit"):
            client.page(MAILBOX, START, END)
    else:
        assert client.page(MAILBOX, START, END) == {"value": []}
