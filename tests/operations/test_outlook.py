import json
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta

import pytest

from edn.connectors.errors import SourceUnavailableError
from edn.operations.outlook import OperationsOutlookClient, ingest_mailbox
from edn.operations.storage import EventStore

START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 10, 2, tzinfo=UTC)
MAILBOX = "edn@example.com"
NEXT = "https://graph.microsoft.com/v1.0/users/edn%40example.com/mailFolders/inbox/messages?$skip=50"


class Token:
    def acquire_token(self):
        return "synthetic"


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.payload).encode()


def message(identifier="m1", **changes):
    return {
        "id": identifier,
        "subject": "Please review",
        "receivedDateTime": "2026-10-01T12:00:00Z",
        "body": {"contentType": "text", "content": "Source body"},
        "from": {"emailAddress": {"address": "client@example.com"}},
        "toRecipients": [{"emailAddress": {"address": MAILBOX}}],
        "attachments": [{"id": "a1", "name": "plan.pdf", "size": 42}],
        "flag": {"flagStatus": "flagged"},
        **changes,
    }


def test_paginated_import_replay_and_provenance(tmp_path):
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        if "$skip" in request.full_url:
            return Response({"value": [message("m2")]})
        return Response({"value": [message(), {"id": "bad"}], "@odata.nextLink": NEXT})

    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,), opener=opener)
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    first = ingest_mailbox(client, store, MAILBOX, START, END)
    assert (first.inserted, first.duplicates, first.failed, first.complete) == (
        2,
        0,
        1,
        False,
    )
    second = ingest_mailbox(client, store, MAILBOX, START, END)
    assert (second.inserted, second.duplicates, second.failed) == (0, 2, 1)
    event = store.list_events()[0]
    assert event.raw_payload["id"] == event.external_id
    assert event.source_account == MAILBOX
    assert event.body == "Source body"
    assert event.parties[0]["address"] == "client@example.com"
    assert event.attachments[0]["name"] == "plan.pdf"
    assert event.needs_action
    assert all(request.method == "GET" for request in requests)
    assert all("ImmutableId" in request.get_header("Prefer") for request in requests)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0].full_url).query)
    assert "body" in query["$select"][0]
    assert "contentBytes" not in query["$expand"][0]


@pytest.mark.parametrize(
    "continuation",
    [
        "https://evil.example/messages",
        NEXT.replace("edn%40", "personal%40"),
        NEXT.replace("/messages?", "/attachments?"),
        "http://graph.microsoft.com/v1.0/",
    ],
)
def test_reject_unsafe_continuations_before_network(continuation):
    def opener(*args, **kwargs):
        pytest.fail("Unsafe URL reached the network")

    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,), opener=opener)
    with pytest.raises(ValueError):
        client.page(MAILBOX, START, END, continuation=continuation)
    with pytest.raises(ValueError):
        client.page("personal@example.com", START, END)


def test_bound_limit_is_not_reported_complete_and_repeated_links_fail(tmp_path):
    client = OperationsOutlookClient(
        Token(),
        mailboxes=(MAILBOX,),
        opener=lambda *a, **k: Response(
            {"value": [message()], "@odata.nextLink": NEXT}
        ),
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    report = ingest_mailbox(client, store, MAILBOX, START, END, max_pages=1)
    assert report.inserted == 1 and not report.complete
    with pytest.raises(ValueError, match="repeated"):
        ingest_mailbox(client, store, MAILBOX, START, END)


def test_unflagged_and_out_of_window_or_html_mail(tmp_path):
    records = [
        message(flag={}),
        message("old", receivedDateTime="2026-09-01T00:00:00Z"),
        message(
            "html", body={"contentType": "html", "content": "<script>bad</script>"}
        ),
    ]
    client = OperationsOutlookClient(
        Token(),
        mailboxes=(MAILBOX,),
        opener=lambda *a, **k: Response({"value": records}),
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    report = ingest_mailbox(client, store, MAILBOX, START, END)
    assert report.inserted == 1 and report.failed == 2
    assert not store.list_events()[0].needs_action


def test_network_failure_leaves_existing_records_retryable(tmp_path):
    def opener(*args, **kwargs):
        raise urllib.error.URLError("failure")

    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,), opener=opener)
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    with pytest.raises(SourceUnavailableError):
        ingest_mailbox(client, store, MAILBOX, START, END)
    assert store.list_events() == ()


@pytest.mark.parametrize(
    "start,end",
    [
        (START.replace(tzinfo=None), END),
        (END, START),
        (START, START + timedelta(days=31, seconds=1)),
    ],
)
def test_invalid_window_never_reaches_network(start, end):
    def opener(*args, **kwargs):
        pytest.fail("Invalid window reached Graph")

    client = OperationsOutlookClient(Token(), mailboxes=(MAILBOX,), opener=opener)
    with pytest.raises(ValueError):
        client.page(MAILBOX, start, end)


def test_multiple_business_mailboxes_keep_same_native_id_separate(tmp_path):
    mailboxes = (
        "elliot@ednsystems.com.au",
        "elliot.daniels@apexcomms.com.au",
        "operations@ednsystems.com.au",
    )
    client = OperationsOutlookClient(
        Token(),
        mailboxes=mailboxes,
        opener=lambda *a, **k: Response({"value": [message()]}),
    )
    store = EventStore(tmp_path / "events.db")
    store.initialise()
    for mailbox in mailboxes:
        assert ingest_mailbox(client, store, mailbox, START, END).inserted == 1
    assert {event.source_account for event in store.list_events()} == set(mailboxes)
    for mailbox in mailboxes:
        assert ingest_mailbox(client, store, mailbox, START, END).duplicates == 1
