from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from edn.connectors import ConnectorRequest, check_connector
from edn.connectors.microsoft_sharepoint import (
    MicrosoftSharePointConnector,
    SharePointConfig,
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
from edn.intelligence import IntelligenceRequest, SharePointEvidenceAdapter

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)
EDN = SecurityDomain("EDN", "EDN", "tenant")
PERSONAL = SecurityDomain("PERSONAL", "Personal", "tenant")
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential")


class FakeSharePointClient:
    def __init__(self, items: tuple[dict[str, Any], ...] = ()) -> None:
        self.items = items
        self.calls = 0

    def search_items(self, site_id, list_id, query, field_names, *, limit):
        self.calls += 1
        return self.items[:limit]

    def list_fields(self, site_id, list_id):
        self.calls += 1
        return ("Title", "IMSDescription", "IMSInformationClassification")


def _config() -> SharePointConfig:
    return SharePointConfig(
        "tenant",
        "site-edn",
        "list-risks",
        "Risks and Opportunities",
        ("Title", "IMSDescription", "IMSInformationClassification"),
        "IMSInformationClassification",
        "EDN Internal",
        EDN,
        CLASSIFICATION,
    )


def _item(identifier: str = "risk-one", security: str = "EDN Internal"):
    return {
        "id": identifier,
        "eTag": '"3"',
        "lastModifiedDateTime": "2026-08-11T10:00:00Z",
        "webUrl": "https://example.sharepoint.com/sites/edn/Lists/Risks/1",
        "fields": {
            "Title": "Supplier continuity risk",
            "IMSDescription": "Review the single-source supplier treatment.",
            "IMSInformationClassification": security,
            "UnapprovedField": "must not enter the projection",
        },
    }


def _request(connector, *, domain=EDN, operation="search") -> ConnectorRequest:
    principal = PrincipalContext("owner", "tenant", frozenset({domain}), True)
    purpose = Purpose("business-intelligence", "Business intelligence")
    capability = f"sharepoint.{operation}"
    permission = PermissionRequest(
        "sharepoint-request",
        principal,
        purpose,
        capability,
        operation,
        domain,
        CLASSIFICATION,
        ("site-edn", "list-risks"),
    )
    manifest = next(
        item
        for item in connector.manifest.capabilities
        if item.capability_id == capability
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
            "sharepoint-test",
            "1",
            (
                PolicyRule(
                    "allow-sharepoint-test",
                    PermissionOutcome.ALLOWED,
                    "Synthetic read-only SharePoint authority.",
                    domain_ids=frozenset({domain.domain_id}),
                    capability_ids=frozenset({capability}),
                    operations=frozenset({operation}),
                ),
            ),
        )
    )
    authority = evaluate_capability_use(registry, policy, permission, now=NOW)
    return ConnectorRequest(
        "sharepoint-request",
        "sharepoint-correlation",
        principal,
        purpose,
        domain,
        CLASSIFICATION,
        capability,
        operation,
        authority,
        ("site-edn", "list-risks"),
    )


def test_connector_is_read_only_conformant_and_least_privilege() -> None:
    connector = MicrosoftSharePointConnector(_config(), FakeSharePointClient())

    assert check_connector(connector).conforms
    assert connector.manifest.supported_operations == {"search", "verify"}
    assert all(
        capability.required_permissions == {"Sites.Selected"}
        for capability in connector.manifest.capabilities
    )
    assert not hasattr(connector, "act")
    assert not hasattr(connector, "sync")


def test_projection_retains_field_security_and_freshness_provenance() -> None:
    connector = MicrosoftSharePointConnector(
        _config(), FakeSharePointClient((_item(),))
    )
    result = connector.search_records(
        _request(connector), query="supplier", now=NOW, limit=5
    )

    assert result.admitted_count == 1
    record = result.records[0]
    assert record.is_fresh(freshness_days=30)
    assert dict(record.fields) == {
        "Title": "Supplier continuity risk",
        "IMSDescription": "Review the single-source supplier treatment.",
        "IMSInformationClassification": "EDN Internal",
    }
    reference = connector.evidence_ref(record)
    assert "security:EDN Internal" in (reference.locator or "")
    assert "modified:" in (reference.locator or "")
    assert reference.record.source_version == '"3"'


def test_security_mismatch_is_filtered_before_evidence() -> None:
    connector = MicrosoftSharePointConnector(
        _config(), FakeSharePointClient((_item(security="PERSONAL"),))
    )
    result = connector.search_records(
        _request(connector), query="supplier", now=NOW, limit=5
    )

    assert result.pre_filter_count == 1
    assert result.admitted_count == 0
    assert result.rejected_count == 1


def test_content_or_permission_payload_fails_closed() -> None:
    unsafe = _item() | {"content": {"value": "not authorised"}}
    connector = MicrosoftSharePointConnector(_config(), FakeSharePointClient((unsafe,)))

    with pytest.raises(ValueError, match="field projection"):
        connector.search_records(
            _request(connector), query="supplier", now=NOW, limit=5
        )


def test_adapter_emits_source_neutral_business_evidence() -> None:
    connector = MicrosoftSharePointConnector(
        _config(), FakeSharePointClient((_item(),))
    )
    connector_request = _request(connector)
    request = IntelligenceRequest(
        "What business risks need attention?",
        connector_request.principal,
        connector_request.purpose,
        connector_request.security_domain,
        connector_request.classification,
    )

    evidence = SharePointEvidenceAdapter(connector).retrieve(
        request, limit=5, now=NOW, authority=connector_request.authority
    )

    assert len(evidence) == 1
    assert evidence[0].source_label == "Business OS SharePoint"
    assert evidence[0].provenance[0].record.record_type == (
        "business.record.sharepoint"
    )
    assert "UnapprovedField" not in evidence[0].excerpt


def test_wrong_domain_fails_before_synthetic_client_call() -> None:
    client = FakeSharePointClient((_item(),))
    connector = MicrosoftSharePointConnector(_config(), client)

    with pytest.raises(ValueError, match="explicitly usable"):
        _request(connector, domain=PERSONAL)

    assert client.calls == 0
