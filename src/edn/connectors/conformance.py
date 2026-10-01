"""Reusable connector validation and Capability Registry integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from edn.connectors.base import (
    ActionConnector,
    AuthenticatableConnector,
    CheckpointingConnector,
    Connector,
    DiscoverableConnector,
    IngestibleConnector,
    InspectableConnector,
    PlannableConnector,
    SearchableConnector,
    SyncableConnector,
    VerifiableConnector,
)
from edn.connectors.errors import InvalidCheckpointError, UnsupportedOperationError
from edn.connectors.models import (
    CONNECTOR_OPERATIONS,
    Checkpoint,
    ConnectorManifest,
    ConnectorPlan,
    ConnectorRequest,
)
from edn.core import CapabilityRegistry, CapabilityRuntimeState, RegisteredCapability


@dataclass(frozen=True, slots=True)
class ConformanceIssue:
    code: str
    explanation: str


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    connector_id: str
    issues: tuple[ConformanceIssue, ...]

    @property
    def conforms(self) -> bool:
        return not self.issues


_PROTOCOLS: dict[str, type[object]] = {
    "discover": DiscoverableConnector,
    "inspect": InspectableConnector,
    "plan": PlannableConnector,
    "authenticate": AuthenticatableConnector,
    "ingest": IngestibleConnector,
    "sync": SyncableConnector,
    "checkpoint": CheckpointingConnector,
    "resume": CheckpointingConnector,
    "search": SearchableConnector,
    "act": ActionConnector,
    "verify": VerifiableConnector,
}


def check_connector(connector: Connector) -> ConformanceReport:
    manifest = connector.manifest
    issues: list[ConformanceIssue] = []
    try:
        if ConnectorManifest.from_dict(manifest.to_dict()) != manifest:
            issues.append(ConformanceIssue("manifest_round_trip", "Manifest changed."))
    except (KeyError, TypeError, ValueError):
        issues.append(
            ConformanceIssue("manifest_round_trip", "Manifest failed validation.")
        )
    for operation in sorted(CONNECTOR_OPERATIONS):
        declared = operation in manifest.supported_operations
        protocol = _PROTOCOLS[operation]
        implemented = isinstance(connector, protocol)
        if declared and not implemented:
            issues.append(
                ConformanceIssue(
                    "declared_operation_missing",
                    f"Declared operation {operation} has no protocol implementation.",
                )
            )
        if implemented and not declared:
            issues.append(
                ConformanceIssue(
                    "undeclared_operation_implemented",
                    f"Implemented operation {operation} is not declared.",
                )
            )
    return ConformanceReport(manifest.connector_id, tuple(issues))


def require_supported_operation(
    connector: Connector, request: ConnectorRequest
) -> None:
    manifest = connector.manifest
    if request.operation not in manifest.supported_operations:
        raise UnsupportedOperationError(
            f"Operation {request.operation} is not declared by this connector.",
            connector_id=manifest.connector_id,
        )
    if request.capability_id not in {
        capability.capability_id for capability in manifest.capabilities
    }:
        raise UnsupportedOperationError(
            "Requested capability is not declared by this connector.",
            connector_id=manifest.connector_id,
        )


def validate_plan_binding(
    first: ConnectorPlan,
    repeated: ConnectorPlan,
    changed_scope: ConnectorPlan,
) -> tuple[ConformanceIssue, ...]:
    issues = []
    if first.to_json() != repeated.to_json() or first.plan_hash != repeated.plan_hash:
        issues.append(
            ConformanceIssue("plan_not_deterministic", "Equivalent plans differ.")
        )
    if (
        first.scope != changed_scope.scope
        and first.plan_hash == changed_scope.plan_hash
    ):
        issues.append(
            ConformanceIssue("plan_scope_not_bound", "Plan hash ignores scope changes.")
        )
    return tuple(issues)


def require_compatible_checkpoint(
    checkpoint: Checkpoint,
    manifest: ConnectorManifest,
    configuration_hash: str,
) -> None:
    if not checkpoint.is_compatible(
        connector_id=manifest.connector_id,
        connector_version=manifest.version,
        configuration_hash=configuration_hash,
    ):
        raise InvalidCheckpointError(
            "Checkpoint is incompatible with connector version or configuration.",
            connector_id=manifest.connector_id,
        )


class RuntimeStateFactory(Protocol):
    def __call__(
        self, capability_id: str, manifest: ConnectorManifest
    ) -> CapabilityRuntimeState: ...


def register_manifest_capabilities(
    manifest: ConnectorManifest,
    registry: CapabilityRegistry,
    runtime_factory: RuntimeStateFactory,
) -> tuple[RegisteredCapability, ...]:
    registered = []
    for capability in sorted(
        manifest.capabilities, key=lambda item: item.capability_id
    ):
        registered.append(
            registry.register(
                capability, runtime_factory(capability.capability_id, manifest)
            )
        )
    return tuple(registered)
