from __future__ import annotations

import json
import urllib.parse
from datetime import UTC, datetime
from typing import Any

import pytest

from edn.connectors import ConnectorRequest, check_connector
from edn.connectors.microsoft_outlook import (
    MailScopeMode,
    MailWindow,
    MicrosoftGraphOutlookClient,
    MicrosoftOutlookConnector,
    OutlookConfig,
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
from edn.intelligence import IntelligenceRequest, OutlookEvidenceAdapter

NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)
EDN = SecurityDomain("EDN", "EDN", "tenant")
PERSONAL = SecurityDomain("PERSONAL", "Personal", "tenant")
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential")


class _Response:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.value).encode()


class _Token:
    def acquire_token(self) -> str:
        return "synthetic-token"


class FakeOutlookClient:
    def __init__(self, messages: tuple[dict[str, Any], ...] = ()) -> None:
        self.items = messages
        self.calls = 0

    def messages(self, mailbox_id, folder_id, start, end, *, limit):
        self.calls += 1
        return tuple(
            item for item in self.items if item.get("parentFolderId") == folder_id
        )[:limit]

    def folders(self, mailbox_id):
        return ({"id": "inbox"},)


def _config(*, category_required: bool = False) -> OutlookConfig:
    return OutlookConfig(
        "tenant",
        "owner@example.com",
        "owner-mailbox",
        ("inbox",),
        EDN,
        CLASSIFICATION,
        MailScopeMode.CATEGORY_REQUIRED
        if category_required
        else MailScopeMode.DEDICATED_EDN,
        "EDN" if category_required else None,
    )


def _message(identifier: str = "message-one", categories=("EDN",)):
    return {
        "id": identifier,
        "parentFolderId": "inbox",
        "subject": "Client approval required",
        "from": {"emailAddress": {"address": "client@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "owner@example.com"}}],
        "receivedDateTime": "2026-08-11T10:00:00Z",
        "lastModifiedDateTime": "2026-08-11T10:05:00Z",
        "importance": "high",
        "isRead": False,
        "categories": list(categories),
        "webLink": "https://outlook.office.com/mail/item",
    }


def _request(connector, *, domain=EDN) -> ConnectorRequest:
    principal = PrincipalContext("owner", "tenant", frozenset({domain}), True)
    purpose = Purpose("current-mail", "Current mail intelligence")
    scope = ("owner-mailbox", "inbox", "window:last-7-days")
    permission = PermissionRequest(
        "outlook-request",
        principal,
        purpose,
        "outlook.search",
        "search",
        domain,
        CLASSIFICATION,
        scope,
    )
    manifest = next(
        item
        for item in connector.manifest.capabilities
        if item.capability_id == "outlook.search"
    )
    registry = CapabilityRegistry()
    registry.register(
        manifest,
        CapabilityRuntimeState(
            CapabilityStatus.READY,
            AuthenticationStatus.VALID,
            health="synthetic",
        ),
    )
    policy = PermissionEvaluator(
        PolicySet(
            "outlook-test",
            "1",
            (
                PolicyRule(
                    "allow-outlook-test",
                    PermissionOutcome.ALLOWED,
                    "Synthetic read-only mail authority.",
                    domain_ids=frozenset({domain.domain_id}),
                    capability_ids=frozenset({"outlook.search"}),
                    operations=frozenset({"search"}),
                ),
            ),
        )
    )
    authority = evaluate_capability_use(registry, policy, permission, now=NOW)
    return ConnectorRequest(
        "outlook-request",
        "outlook-correlation",
        principal,
        purpose,
        domain,
        CLASSIFICATION,
        "outlook.search",
        "search",
        authority,
        scope,
    )


def test_connector_is_read_only_and_conformant() -> None:
    connector = MicrosoftOutlookConnector(_config(), FakeOutlookClient())

    assert check_connector(connector).conforms
    assert connector.manifest.supported_operations == {"search", "verify"}
    assert all(
        item.required_permissions == {"Mail.Read"}
        for item in connector.manifest.capabilities
    )
    assert not hasattr(connector, "act")


def test_live_client_is_get_only_inbox_metadata_and_fails_closed() -> None:
    requests = []

    def opener(request, *, timeout):
        assert timeout == 30
        requests.append(request)
        if "/mailFolders/inbox?" in request.full_url:
            return _Response({"id": "native-inbox", "displayName": "Inbox"})
        return _Response({"value": [_message()]})

    client = MicrosoftGraphOutlookClient(_Token(), opener=opener)
    folders = client.folders("me")
    result = client.messages(
        "me", "native-inbox", NOW.replace(day=4), NOW, limit=25
    )

    assert folders[0]["id"] == "native-inbox"
    assert result[0]["id"] == "message-one"
    assert all(request.method == "GET" for request in requests)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[-1].full_url).query)
    assert query["$top"] == ["25"]
    projection = query["$select"][0]
    assert all(
        excluded not in projection
        for excluded in ("body", "bodyPreview", "attachments", "uniqueBody")
    )
    with pytest.raises(ValueError, match="Inbox must be resolved"):
        client.messages("me", "other-folder", NOW.replace(day=4), NOW, limit=25)
    with pytest.raises(ValueError, match="only /me"):
        client.folders("another-user")


def test_current_mail_metadata_is_bounded_and_body_payload_fails_closed() -> None:
    connector = MicrosoftOutlookConnector(_config(), FakeOutlookClient((_message(),)))
    result = connector.search_messages(
        _request(connector), window=MailWindow.LAST_7_DAYS, now=NOW, limit=5
    )

    assert result.pre_filter_count == result.admitted_count == 1
    assert result.messages[0].subject == "Client approval required"
    assert result.messages[0].recipients == ("owner@example.com",)
    assert result.messages[0].security_domain == EDN

    unsafe = _message() | {"bodyPreview": "must not enter context"}
    unsafe_connector = MicrosoftOutlookConnector(
        _config(), FakeOutlookClient((unsafe,))
    )
    with pytest.raises(ValueError, match="metadata projection"):
        unsafe_connector.search_messages(
            _request(unsafe_connector),
            window=MailWindow.LAST_7_DAYS,
            now=NOW,
            limit=5,
        )


def test_category_filter_counts_rejected_without_content_leakage() -> None:
    client = FakeOutlookClient(
        (_message("business"), _message("personal", categories=("Personal",)))
    )
    connector = MicrosoftOutlookConnector(_config(category_required=True), client)

    result = connector.search_messages(
        _request(connector), window=MailWindow.LAST_7_DAYS, now=NOW, limit=5
    )

    assert (result.pre_filter_count, result.admitted_count, result.rejected_count) == (
        2,
        1,
        1,
    )
    assert result.messages[0].message_id == "business"


def test_outlook_adapter_emits_source_neutral_metadata_evidence() -> None:
    connector = MicrosoftOutlookConnector(_config(), FakeOutlookClient((_message(),)))
    connector_request = _request(connector)
    request = IntelligenceRequest(
        "What arrived today?",
        connector_request.principal,
        connector_request.purpose,
        connector_request.security_domain,
        connector_request.classification,
    )

    evidence = OutlookEvidenceAdapter(connector).retrieve(
        request, limit=5, now=NOW, authority=connector_request.authority
    )

    assert len(evidence) == 1
    assert evidence[0].source_label == "Current Outlook mail"
    assert evidence[0].provenance[0].record.record_type == (
        "communication.email.metadata"
    )
    assert "body" not in evidence[0].excerpt.casefold()


def test_wrong_domain_fails_before_synthetic_client_call() -> None:
    client = FakeOutlookClient((_message(),))
    connector = MicrosoftOutlookConnector(_config(), client)

    with pytest.raises(ValueError, match="explicitly usable"):
        _request(connector, domain=PERSONAL)

    assert client.calls == 0
