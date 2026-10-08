"""Graph 200 transport failures remain typed and content-safe."""

import io
import json
import traceback

import pytest

from edn.connectors.errors import SourceUnavailableError
from edn.connectors.microsoft_calendar.client import MicrosoftGraphCalendarClient
from edn.connectors.microsoft_outlook.client import MicrosoftGraphOutlookClient


class Token:
    def acquire_token(self):
        return "PRIVATE_SYNTHETIC_TOKEN"


@pytest.mark.parametrize(
    "client_type", [MicrosoftGraphCalendarClient, MicrosoftGraphOutlookClient]
)
@pytest.mark.parametrize(
    "content",
    [
        b'{"PRIVATE_SYNTHETIC_PAYLOAD":',
        b"\xffPRIVATE_SYNTHETIC_PAYLOAD",
        b"[" * 10000 + b"0" + b"]" * 10000,
        b"null",
        b"[]",
        b'"PRIVATE_SYNTHETIC_PAYLOAD"',
    ],
    ids=["invalid-json", "invalid-encoding", "deep-json", "null", "array", "string"],
)
def test_malformed_200_is_typed_without_payload_or_token(client_type, content):
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        assert kwargs == {"timeout": 30}
        return io.BytesIO(content)

    client = client_type(Token(), opener=opener)
    with pytest.raises(SourceUnavailableError) as caught:
        client._get("https://graph.microsoft.com/v1.0/me")
    assert caught.value.code == "source_unavailable"
    diagnostic = json.dumps(caught.value.to_dict()) + "".join(
        traceback.format_exception(caught.value)
    )
    assert "PRIVATE_SYNTHETIC_PAYLOAD" not in diagnostic
    assert "PRIVATE_SYNTHETIC_TOKEN" not in diagnostic
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [{"value": None}, {"value": {}}, {"value": [None]}])
@pytest.mark.parametrize("kind", ["calendar", "outlook"])
def test_invalid_collection_is_typed_and_does_not_follow_continuation(kind, payload):
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        return io.BytesIO(json.dumps(payload | {"@odata.nextLink": "PRIVATE"}).encode())

    if kind == "calendar":
        client = MicrosoftGraphCalendarClient(Token(), opener=opener)
        read = client.calendars
    else:
        client = MicrosoftGraphOutlookClient(Token(), opener=opener)
        def read():
            return client._values("https://graph.microsoft.com/v1.0/me/messages")
    with pytest.raises(SourceUnavailableError):
        read()
    assert len(requests) == 1


def test_outlook_inbox_resolution_failure_is_typed():
    client = MicrosoftGraphOutlookClient(
        Token(), opener=lambda *_a, **_k: io.BytesIO(b'{"id": null}')
    )
    with pytest.raises(SourceUnavailableError):
        client.folders("me")


@pytest.mark.parametrize(
    "client_type", [MicrosoftGraphCalendarClient, MicrosoftGraphOutlookClient]
)
def test_valid_object_is_preserved(client_type):
    client = client_type(
        Token(), opener=lambda *_a, **_k: io.BytesIO(b'{"value": [{"id": "one"}]}')
    )
    assert client._get("https://graph.microsoft.com/v1.0/me") == {
        "value": [{"id": "one"}]
    }
