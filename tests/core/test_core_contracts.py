from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from edn.core import (
    CapabilityDecision,
    CapabilityManifest,
    CapabilityStatus,
    Classification,
    EvidenceRef,
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    SourceRef,
    UniversalRecordRef,
    count_eligible_evidence,
    filter_eligible_evidence,
    is_evidence_eligible,
)


def domain(domain_id: str, tenant: str = "tenant-one") -> SecurityDomain:
    return SecurityDomain(domain_id, domain_id.title(), tenant)


def context(*domains: SecurityDomain, tenant: str = "tenant-one") -> PrincipalContext:
    return PrincipalContext("user-1", tenant, frozenset(domains), True)


def evidence(item_id: str, security_domain: SecurityDomain) -> EvidenceRef:
    classification = Classification("scheme-one", "internal", "Internal", 1)
    source = SourceRef("source-1", "connector-1", "instance-1", "Synthetic")
    record = UniversalRecordRef(
        source,
        item_id,
        security_domain,
        classification,
        "message",
        f"urn:test:{item_id}",
    )
    return EvidenceRef(f"evidence-{item_id}", record, locator="paragraph:1")


def test_domain_identity_is_durable_and_tenant_aware() -> None:
    first = SecurityDomain("CLIENT:a", "Client A", "tenant-one")
    renamed = SecurityDomain("CLIENT:a", "Renamed A", "tenant-one")
    other_tenant = SecurityDomain("CLIENT:a", "Client A", "tenant-two")
    assert first == renamed
    assert first != other_tenant
    assert SecurityDomain.from_dict(first.to_dict()) == first
    with pytest.raises(ValueError):
        SecurityDomain("CLIENT::a", "Bad", "tenant-one")


def test_principal_context_is_immutable_and_fail_closed() -> None:
    edn = domain("EDN")
    principal = context(edn)
    with pytest.raises(FrozenInstanceError):
        principal.principal_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        context()
    with pytest.raises(ValueError):
        PrincipalContext("user", "tenant-one", frozenset({edn}), False)
    malformed = principal.to_dict()
    malformed["authenticated"] = "yes"
    with pytest.raises(ValueError):
        PrincipalContext.from_dict(malformed)


def test_security_domain_isolation_filtering_and_counts() -> None:
    edn = domain("EDN")
    personal = domain("PERSONAL")
    client_a = domain("CLIENT:a")
    client_b = domain("CLIENT:b")
    items = [
        evidence("edn", edn),
        evidence("personal", personal),
        evidence("a", client_a),
    ]

    edn_context = context(edn)
    assert is_evidence_eligible(edn_context, items[0])
    assert not is_evidence_eligible(edn_context, items[1])
    assert is_evidence_eligible(context(personal), items[1])
    assert not is_evidence_eligible(context(client_a), evidence("b", client_b))
    assert filter_eligible_evidence(edn_context, items) == (items[0],)
    assert count_eligible_evidence(edn_context, items) == 1
    assert count_eligible_evidence(None, items) == 0

    widened_then_narrowed = evidence("follow-up", personal)
    assert is_evidence_eligible(context(personal), widened_then_narrowed)
    assert not is_evidence_eligible(edn_context, widened_then_narrowed)


def test_reference_round_trip_and_secret_rejection() -> None:
    item = evidence("round-trip", domain("EDN"))
    assert EvidenceRef.from_dict(item.to_dict()) == item
    assert item.to_json() == EvidenceRef.from_dict(item.to_dict()).to_json()
    with pytest.raises(KeyError):
        UniversalRecordRef.from_dict(
            {
                "schema_version": "1.0.0",
                "source": item.record.source.to_dict(),
                "source_record_key": "record",
                "security_domain": item.record.security_domain.to_dict(),
                "record_type": "message",
            }
        )
    with pytest.raises(ValueError):
        UniversalRecordRef(
            item.record.source,
            "record",
            item.record.security_domain,
            item.record.classification,
            "message",
            "https://example.test/item?access_token=secret",
        )


def test_capability_contracts_are_explicit_and_deterministic() -> None:
    manifest = CapabilityManifest(
        "mail.search",
        "provider-one",
        "connector-one",
        "1.0.0",
        frozenset({"search", "read"}),
        frozenset({"mail.read"}),
        frozenset({"domain.explicit"}),
        "read",
    )
    assert CapabilityManifest.from_dict(manifest.to_dict()) == manifest
    assert manifest.to_dict()["operations"] == ["read", "search"]
    unknown = CapabilityDecision(
        "mail.search",
        CapabilityStatus.INDETERMINATE,
        "runtime.unknown",
        "Unknown state",
    )
    assert not unknown.is_usable
    assert CapabilityDecision.from_dict(unknown.to_dict()) == unknown


def test_permission_contracts_fail_closed_and_round_trip() -> None:
    edn = domain("EDN")
    request = PermissionRequest(
        "request-1",
        context(edn),
        Purpose("retrieve", "Retrieve evidence"),
        "mail.search",
        "read",
        edn,
        Classification("scheme-one", "internal", "Internal"),
        ("mailbox-one",),
    )
    assert PermissionRequest.from_dict(request.to_dict()) == request
    indeterminate = PermissionDecision(
        "request-1", PermissionOutcome.INDETERMINATE, "No matching policy"
    )
    assert not indeterminate.is_allowed()
    assert PermissionDecision.from_dict(indeterminate.to_dict()) == indeterminate

    expiry = datetime.now(UTC) + timedelta(minutes=10)
    temporary = PermissionDecision(
        "request-1",
        PermissionOutcome.TEMPORARILY_ALLOWED,
        "Owner approved",
        expires_at=expiry,
        approval_ref="approval-1",
    )
    assert temporary.is_allowed(at=expiry - timedelta(seconds=1))
    assert not temporary.is_allowed(at=expiry)
    with pytest.raises(ValueError):
        PermissionDecision("request-1", PermissionOutcome.TEMPORARILY_ALLOWED, "Bad")
    malformed = indeterminate.to_dict()
    malformed["outcome"] = "maybe"
    with pytest.raises(ValueError):
        PermissionDecision.from_dict(malformed)


def test_second_tenant_uses_same_platform_contracts() -> None:
    second_domain = SecurityDomain("WORKSPACE:west", "West Workspace", "tenant-two")
    second_classification = Classification("acme-scheme", "sensitive", "Sensitive")
    second_principal = PrincipalContext(
        "acme-user", "tenant-two", frozenset({second_domain}), True, "service"
    )
    second_record = UniversalRecordRef(
        SourceRef("acme-source", "files", "west-drive", "West Drive"),
        "record-99",
        second_domain,
        second_classification,
        "file",
    )
    assert is_evidence_eligible(
        second_principal, EvidenceRef("evidence-99", second_record)
    )
    assert second_classification.scheme_id == "acme-scheme"
