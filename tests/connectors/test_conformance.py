from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from edn.connectors import (
    ActionResult,
    Checkpoint,
    ConnectorError,
    ConnectorManifest,
    ConnectorPlan,
    ConnectorRequest,
    DiscoveryResult,
    IngestResult,
    InspectionResult,
    InvalidCheckpointError,
    ResourceCandidate,
    SearchResult,
    UnsupportedOperationError,
    VerificationResult,
    VerificationStatus,
    check_connector,
    register_manifest_capabilities,
    require_compatible_checkpoint,
    require_supported_operation,
    validate_plan_binding,
)
from edn.core import (
    AuthenticationStatus,
    CapabilityManifest,
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

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CONFIG_HASH = "c" * 64


def capability(
    connector_id: str, capability_id: str, operations: frozenset[str]
) -> CapabilityManifest:
    return CapabilityManifest(
        capability_id,
        "synthetic-provider",
        connector_id,
        "1.0.0",
        operations,
        frozenset({"synthetic.read"}),
        frozenset({"TEST"}),
        "read",
    )


def connector_manifest(
    connector_id: str, capabilities: tuple[CapabilityManifest, ...]
) -> ConnectorManifest:
    operations = frozenset(
        operation for item in capabilities for operation in item.operations
    )
    return ConnectorManifest(
        connector_id,
        "1.0.0",
        connector_id.title(),
        "synthetic-provider",
        "Synthetic conformance connector.",
        "synthetic",
        capabilities,
        operations,
        f"urn:schema:{connector_id}:1",
        "1.0.0",
    )


FILES_CAPABILITIES = (
    capability("synthetic-files", "synthetic-files.discover", frozenset({"discover"})),
    capability("synthetic-files", "synthetic-files.inspect", frozenset({"inspect"})),
    capability("synthetic-files", "synthetic-files.ingest", frozenset({"ingest"})),
    capability("synthetic-files", "synthetic-files.verify", frozenset({"verify"})),
)
ACCOUNTING_CAPABILITIES = (
    capability("synthetic-accounting", "accounting.search", frozenset({"search"})),
    capability("synthetic-accounting", "accounting.plan", frozenset({"plan"})),
    capability("synthetic-accounting", "accounting.act", frozenset({"act"})),
    capability("synthetic-accounting", "accounting.verify", frozenset({"verify"})),
)


class SyntheticFilesConnector:
    manifest = connector_manifest("synthetic-files", FILES_CAPABILITIES)

    def discover(self, request: ConnectorRequest) -> DiscoveryResult:
        require_supported_operation(self, request)
        resource = ResourceCandidate(
            "resource-one",
            "file",
            "urn:synthetic:file:one",
            request.security_domain,
            request.classification,
            size_bytes=128,
            modified_at=NOW,
            already_known=False,
            required_permissions=("synthetic.read",),
        )
        return DiscoveryResult(request.request_id, (resource,))

    def inspect(self, request: ConnectorRequest) -> InspectionResult:
        require_supported_operation(self, request)
        resource = ResourceCandidate(
            "resource-one",
            "file",
            "urn:synthetic:file:one",
            request.security_domain,
            request.classification,
            size_bytes=128,
            modified_at=NOW,
        )
        return InspectionResult(request.request_id, resource, ("metadata-only",))

    def ingest(
        self, request: ConnectorRequest, checkpoint: Checkpoint | None = None
    ) -> IngestResult:
        require_supported_operation(self, request)
        return IngestResult(request.request_id, (), checkpoint)

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        require_supported_operation(self, request)
        return VerificationResult(
            request.request_id, VerificationStatus.VERIFIED, "Synthetic verification."
        )


class SyntheticAccountingConnector:
    manifest = connector_manifest("synthetic-accounting", ACCOUNTING_CAPABILITIES)

    def search(self, request: ConnectorRequest) -> SearchResult:
        require_supported_operation(self, request)
        return SearchResult(request.request_id, ())

    def plan(self, request: ConnectorRequest) -> ConnectorPlan:
        require_supported_operation(self, request)
        return ConnectorPlan(
            "plan-one",
            self.manifest.connector_id,
            self.manifest.version,
            request.capability_id,
            request.operation,
            request.scope,
            ("synthetic.write",),
            ("create draft invoice",),
            "external_side_effect",
            ("external invoice may be sent",),
            True,
            1,
            0,
        )

    def act(
        self, request: ConnectorRequest, approved_plan: ConnectorPlan
    ) -> ActionResult:
        require_supported_operation(self, request)
        verification = VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED,
            "Synthetic action verified.",
        )
        return ActionResult(
            request.request_id,
            approved_plan.plan_id,
            approved_plan.plan_hash,
            1,
            verification,
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        require_supported_operation(self, request)
        return VerificationResult(
            request.request_id, VerificationStatus.VERIFIED, "Synthetic verification."
        )


def runtime_factory(
    capability_id: str, manifest: ConnectorManifest
) -> CapabilityRuntimeState:
    assert capability_id
    assert manifest.connector_id
    return CapabilityRuntimeState(
        CapabilityStatus.UNAVAILABLE,
        AuthenticationStatus.NOT_REQUIRED,
        health="unknown",
        last_verified_at=NOW,
        explanation="Installed but not verified.",
    )


def authorized_request(
    manifest: ConnectorManifest,
    capability_id: str,
    operation: str,
    *,
    scope: tuple[str, ...] = ("scope-one",),
    allow: bool = True,
) -> ConnectorRequest:
    test_domain = SecurityDomain("TEST", "Test", "tenant-test")
    principal = PrincipalContext(
        "principal-test", "tenant-test", frozenset({test_domain}), True
    )
    purpose = Purpose("conformance", "Synthetic conformance")
    classification = Classification("test-scheme", "internal", "Internal")
    permission_request = PermissionRequest(
        "permission-request",
        principal,
        purpose,
        capability_id,
        operation,
        test_domain,
        classification,
        scope,
    )
    registry = CapabilityRegistry()
    target = next(
        item for item in manifest.capabilities if item.capability_id == capability_id
    )
    registry.register(
        target,
        CapabilityRuntimeState(
            CapabilityStatus.READY,
            AuthenticationStatus.NOT_REQUIRED,
            health="healthy",
            last_verified_at=NOW,
        ),
    )
    rules = (
        (
            PolicyRule(
                "conformance-allow",
                PermissionOutcome.ALLOWED,
                "Synthetic test authority.",
                tenant_ids=frozenset({"tenant-test"}),
                domain_ids=frozenset({"TEST"}),
                capability_ids=frozenset({capability_id}),
                operations=frozenset({operation}),
            ),
        )
        if allow
        else ()
    )
    decision = evaluate_capability_use(
        registry,
        PermissionEvaluator(PolicySet("test-policy", "1.0.0", rules)),
        permission_request,
        now=NOW,
    )
    return ConnectorRequest(
        "connector-request",
        "correlation-one",
        principal,
        purpose,
        test_domain,
        classification,
        capability_id,
        operation,
        decision,
        scope,
    )


@pytest.mark.parametrize(
    "connector", [SyntheticFilesConnector(), SyntheticAccountingConnector()]
)
def test_different_connector_shapes_pass_shared_conformance(connector: object) -> None:
    report = check_connector(connector)  # type: ignore[arg-type]
    assert report.conforms, report.issues


def test_manifest_is_deterministic_hashed_and_rejects_drift() -> None:
    manifest = SyntheticFilesConnector.manifest
    assert ConnectorManifest.from_dict(manifest.to_dict()) == manifest
    assert (
        manifest.to_json() == ConnectorManifest.from_dict(manifest.to_dict()).to_json()
    )
    changed = manifest.to_dict()
    changed["description"] = "Changed description"
    with pytest.raises(ValueError, match="hash"):
        ConnectorManifest.from_dict(changed)


def test_manifest_rejects_duplicates_mismatch_and_credentials() -> None:
    first = FILES_CAPABILITIES[0]
    with pytest.raises(ValueError, match="unique"):
        connector_manifest("synthetic-files", (first, first))
    with pytest.raises(ValueError, match="connector_id"):
        connector_manifest("different-id", (first,))
    with pytest.raises(ValueError, match="secret"):
        replace(
            SyntheticFilesConnector.manifest,
            configuration_schema_ref="https://example.test/schema?access_token=secret",
        )


def test_metadata_first_discovery_contains_no_payload() -> None:
    connector = SyntheticFilesConnector()
    result = connector.discover(
        authorized_request(connector.manifest, "synthetic-files.discover", "discover")
    )
    candidate = result.resources[0]
    assert candidate.resource_id == "resource-one"
    assert candidate.size_bytes == 128
    assert not hasattr(candidate, "content")
    inspection = connector.inspect(
        authorized_request(connector.manifest, "synthetic-files.inspect", "inspect")
    )
    assert inspection.observations == ("metadata-only",)


def test_plan_is_deterministic_and_scope_bound() -> None:
    connector = SyntheticAccountingConnector()
    first = connector.plan(
        authorized_request(connector.manifest, "accounting.plan", "plan")
    )
    repeated = connector.plan(
        authorized_request(connector.manifest, "accounting.plan", "plan")
    )
    changed = connector.plan(
        authorized_request(
            connector.manifest, "accounting.plan", "plan", scope=("scope-two",)
        )
    )
    assert not validate_plan_binding(first, repeated, changed)
    assert first.plan_hash != changed.plan_hash
    assert ConnectorPlan.from_dict(first.to_dict()) == first


def test_checkpoint_round_trip_and_compatibility() -> None:
    checkpoint = Checkpoint(
        "checkpoint-one",
        "synthetic-files",
        "1.0.0",
        CONFIG_HASH,
        "ingest",
        ("scope-one",),
        "record-100",
        100,
        NOW,
    )
    assert Checkpoint.from_dict(checkpoint.to_dict()) == checkpoint
    require_compatible_checkpoint(
        checkpoint, SyntheticFilesConnector.manifest, CONFIG_HASH
    )
    with pytest.raises(InvalidCheckpointError):
        require_compatible_checkpoint(
            checkpoint, SyntheticFilesConnector.manifest, "d" * 64
        )


def test_indeterminate_authority_cannot_form_connector_request() -> None:
    with pytest.raises(ValueError, match="usable authority"):
        authorized_request(
            SyntheticFilesConnector.manifest,
            "synthetic-files.discover",
            "discover",
            allow=False,
        )


def test_unsupported_operation_is_machine_readable() -> None:
    connector = SyntheticFilesConnector()
    accounting_request = authorized_request(
        SyntheticAccountingConnector.manifest, "accounting.search", "search"
    )
    with pytest.raises(UnsupportedOperationError) as captured:
        require_supported_operation(connector, accounting_request)
    assert captured.value.code == "unsupported_operation"
    assert "search" in captured.value.explanation


def test_safe_error_model_rejects_multiline_or_oversized_content() -> None:
    error = ConnectorError("Safe explanation.", connector_id="synthetic-files")
    assert error.to_dict()["code"] == "connector_error"
    with pytest.raises(ValueError):
        ConnectorError("unsafe\nsource content")
    with pytest.raises(ValueError):
        ConnectorError("x" * 513)


def test_verification_indeterminate_is_not_success() -> None:
    result = VerificationResult(
        "operation-one", VerificationStatus.INDETERMINATE, "Unable to verify."
    )
    assert not result.is_verified


def test_manifest_registers_deterministically_but_not_ready() -> None:
    registry = CapabilityRegistry()
    registered = register_manifest_capabilities(
        SyntheticAccountingConnector.manifest, registry, runtime_factory
    )
    assert [item.manifest.capability_id for item in registered] == sorted(
        item.capability_id for item in ACCOUNTING_CAPABILITIES
    )
    assert all(
        item.runtime.status is CapabilityStatus.UNAVAILABLE for item in registered
    )


def test_conformance_reports_undeclared_implementation() -> None:
    class BadConnector:
        manifest = connector_manifest(
            "bad-connector",
            (capability("bad-connector", "bad.discover", frozenset({"discover"})),),
        )

        def discover(self, request: ConnectorRequest) -> DiscoveryResult:
            return DiscoveryResult(request.request_id, ())

        def search(self, request: ConnectorRequest) -> SearchResult:
            return SearchResult(request.request_id, ())

    report = check_connector(BadConnector())
    assert not report.conforms
    assert "undeclared_operation_implemented" in {issue.code for issue in report.issues}
