"""Operations pagination retains the authenticated read contract."""

import urllib.parse

import pytest

from edn.operations.outlook import OperationsOutlookClient
from tests.operations.test_outlook import (
    END,
    MAILBOX,
    NEXT,
    ORIGINAL,
    QUERY,
    START,
    Response,
)


class CountingToken:
    calls = 0

    def acquire_token(self):
        self.calls += 1
        return "synthetic"


def continuation(fields):
    return ORIGINAL.split("?", 1)[0] + "?" + urllib.parse.urlencode(fields)


@pytest.mark.parametrize(
    "cursor,value",
    [
        ("$skip", "0"),
        ("$skip", "50"),
        ("$skiptoken", "opaque+/= value"),
    ],
)
def test_bounded_continuation_reaches_get_without_rewriting(cursor, value):
    token = CountingToken()
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        return Response({"value": []})

    client = OperationsOutlookClient(token, mailboxes=(MAILBOX,), opener=opener)
    url = continuation({**QUERY, cursor: value})
    assert client.page(MAILBOX, START, END, continuation=url) == {"value": []}
    assert token.calls == 1
    assert requests[0].full_url == url
    assert requests[0].method == "GET"
    assert "ImmutableId" in requests[0].get_header("Prefer")


UNSAFE = [
    17,
    "",
    ORIGINAL,
    NEXT + "#",
    NEXT + "#fragment",
    " " + NEXT,
    "\n" + NEXT,
    NEXT.replace("graph.microsoft.com", "graph.microsoft.\tcom"),
    NEXT + "\r",
    NEXT.replace("https://", "https://user@"),
    NEXT.replace("graph.microsoft.com", "graph.microsoft.com:443"),
    NEXT.replace("https://", "http://"),
    NEXT.replace("/messages?", "/messages/../messages?"),
    NEXT.replace("edn%40", "other%40"),
    NEXT + "&$skip=50",
    NEXT + "&$skiptoken=x",
    NEXT + "&unknown=x",
    NEXT + "&$select=body",
    NEXT + "&broken",
    NEXT + "%xx",
    NEXT + "\x7f",
]
for field in QUERY:
    UNSAFE.append(continuation({**QUERY, field: "changed", "$skip": "50"}))
    UNSAFE.append(
        continuation(
            {
                key: value
                for key, value in {**QUERY, "$skip": "50"}.items()
                if key != field
            }
        )
    )
for value in ("", " ", "-1", "+1", "01", "1.0", "\u0661", "1e2"):
    UNSAFE.append(continuation({**QUERY, "$skip": value}))
for value in ("", " "):
    UNSAFE.append(continuation({**QUERY, "$skiptoken": value}))


@pytest.mark.parametrize("url", UNSAFE)
def test_unsafe_continuation_rejected_before_token_and_transport(url):
    token = CountingToken()

    def opener(*args, **kwargs):
        pytest.fail("Unsafe continuation reached transport")

    client = OperationsOutlookClient(token, mailboxes=(MAILBOX,), opener=opener)
    with pytest.raises(ValueError):
        client.page(MAILBOX, START, END, continuation=url)
    assert token.calls == 0


def test_previous_window_continuation_is_rejected_before_authentication():
    token = CountingToken()

    def opener(*args, **kwargs):
        pytest.fail("Unsafe continuation reached transport")

    client = OperationsOutlookClient(token, mailboxes=(MAILBOX,), opener=opener)
    with pytest.raises(ValueError, match="bounded query"):
        client.page(MAILBOX, START, START, continuation=NEXT)
    assert token.calls == 0


def test_equivalent_query_order_and_encoding_preserve_the_original_url():
    token = CountingToken()
    requests = []

    def opener(request, **kwargs):
        requests.append(request.full_url)
        return Response({"value": []})

    fields = dict(reversed(list(QUERY.items())))
    fields["$skiptoken"] = "opaque"
    url = continuation(fields).replace("+", "%20")
    client = OperationsOutlookClient(token, mailboxes=(MAILBOX,), opener=opener)
    client.page(MAILBOX, START, END, continuation=url)
    assert requests == [url]
    assert token.calls == 1
