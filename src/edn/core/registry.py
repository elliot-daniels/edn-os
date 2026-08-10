"""In-memory capability registry and deterministic availability resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from edn.core.capabilities import (
    CapabilityDecision,
    CapabilityManifest,
    CapabilityStatus,
)
from edn.core.security import SCHEMA_VERSION, SecurityDomain, validate_identifier


class AuthenticationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    VALID = "valid"
    MISSING = "missing"
    EXPIRED = "expired"
    ERROR = "error"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class CapabilityRuntimeState:
    """Supplied runtime facts; this layer performs no probes or authentication."""

    status: CapabilityStatus
    authentication_status: AuthenticationStatus
    unavailable_dependencies: tuple[str, ...] = ()
    missing_permissions: tuple[str, ...] = ()
    health: str = "unknown"
    last_verified_at: datetime | None = None
    explanation: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.health, "health")
        for name, values in (
            ("unavailable_dependencies", self.unavailable_dependencies),
            ("missing_permissions", self.missing_permissions),
        ):
            for value in values:
                validate_identifier(value, name)
        if self.last_verified_at is not None and self.last_verified_at.tzinfo is None:
            raise ValueError("last_verified_at must be timezone-aware")
        if self.explanation is not None and not self.explanation.strip():
            raise ValueError("explanation must not be blank")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status.value,
            "authentication_status": self.authentication_status.value,
            "unavailable_dependencies": list(self.unavailable_dependencies),
            "missing_permissions": list(self.missing_permissions),
            "health": self.health,
            "last_verified_at": _format_datetime(self.last_verified_at),
            "explanation": self.explanation,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            status=CapabilityStatus(value["status"]),
            authentication_status=AuthenticationStatus(value["authentication_status"]),
            unavailable_dependencies=_string_tuple(
                value.get("unavailable_dependencies"), "unavailable_dependencies"
            ),
            missing_permissions=_string_tuple(
                value.get("missing_permissions"), "missing_permissions"
            ),
            health=str(value["health"]),
            last_verified_at=_parse_datetime(value.get("last_verified_at")),
            explanation=_optional_str(value.get("explanation")),
        )


@dataclass(frozen=True, slots=True)
class RegisteredCapability:
    manifest: CapabilityManifest
    runtime: CapabilityRuntimeState

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "manifest": self.manifest.to_dict(),
            "runtime": self.runtime.to_dict(),
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            CapabilityManifest.from_dict(_dict(value["manifest"])),
            CapabilityRuntimeState.from_dict(_dict(value["runtime"])),
        )


class CapabilityRegistry:
    """Bounded in-memory registry with explicit duplicate handling."""

    def __init__(self, capabilities: tuple[RegisteredCapability, ...] = ()) -> None:
        self._capabilities: dict[str, RegisteredCapability] = {}
        for capability in capabilities:
            self.register(capability.manifest, capability.runtime)

    def register(
        self, manifest: CapabilityManifest, runtime: CapabilityRuntimeState
    ) -> RegisteredCapability:
        if manifest.capability_id in self._capabilities:
            raise ValueError(f"capability already registered: {manifest.capability_id}")
        capability = RegisteredCapability(manifest, runtime)
        self._capabilities[manifest.capability_id] = capability
        return capability

    def unregister(self, capability_id: str) -> RegisteredCapability:
        validate_identifier(capability_id, "capability_id")
        try:
            return self._capabilities.pop(capability_id)
        except KeyError as error:
            raise KeyError(f"capability not registered: {capability_id}") from error

    def get(self, capability_id: str) -> RegisteredCapability | None:
        validate_identifier(capability_id, "capability_id")
        return self._capabilities.get(capability_id)

    def list(
        self,
        *,
        status: CapabilityStatus | None = None,
        operation: str | None = None,
    ) -> tuple[RegisteredCapability, ...]:
        if operation is not None:
            validate_identifier(operation, "operation")
        matches = (
            item
            for item in self._capabilities.values()
            if (status is None or item.runtime.status is status)
            and (operation is None or operation in item.manifest.operations)
        )
        return tuple(sorted(matches, key=lambda item: item.manifest.capability_id))

    def resolve(
        self,
        capability_id: str,
        operation: str,
        security_domain: SecurityDomain,
    ) -> CapabilityDecision:
        validate_identifier(capability_id, "capability_id")
        validate_identifier(operation, "operation")
        capability = self._capabilities.get(capability_id)
        if capability is None:
            return _decision(
                capability_id,
                CapabilityStatus.INDETERMINATE,
                "capability_not_registered",
                "The requested capability is not registered.",
                (capability_id,),
            )
        manifest = capability.manifest
        runtime = capability.runtime
        if operation not in manifest.operations:
            return _decision(
                capability_id,
                CapabilityStatus.UNAVAILABLE,
                "operation_not_supported",
                f"Capability does not support operation {operation}.",
                (operation,),
            )
        if security_domain.domain_id not in manifest.supported_domain_scopes:
            return _decision(
                capability_id,
                CapabilityStatus.UNAVAILABLE,
                "domain_not_supported",
                "Capability does not support the requested security domain.",
                (security_domain.domain_id,),
            )
        if runtime.status is CapabilityStatus.DISABLED:
            return _decision(
                capability_id,
                CapabilityStatus.DISABLED,
                "capability_disabled",
                runtime.explanation or "Capability is disabled.",
            )
        if runtime.status is CapabilityStatus.INDETERMINATE:
            return _decision(
                capability_id,
                CapabilityStatus.INDETERMINATE,
                "runtime_indeterminate",
                runtime.explanation or "Capability runtime state is indeterminate.",
            )
        if runtime.authentication_status not in {
            AuthenticationStatus.NOT_REQUIRED,
            AuthenticationStatus.VALID,
        }:
            return _decision(
                capability_id,
                CapabilityStatus.AUTHENTICATION_REQUIRED,
                "authentication_required",
                runtime.explanation or "Valid authentication is required.",
                (runtime.authentication_status.value,),
            )
        if runtime.unavailable_dependencies:
            return _decision(
                capability_id,
                CapabilityStatus.UNAVAILABLE,
                "dependency_unavailable",
                "One or more capability dependencies are unavailable.",
                runtime.unavailable_dependencies,
            )
        if runtime.missing_permissions:
            return _decision(
                capability_id,
                CapabilityStatus.PERMISSION_REQUIRED,
                "permission_required",
                "One or more external permissions are missing.",
                runtime.missing_permissions,
                approval_could_resolve=True,
            )
        reason_codes = {
            CapabilityStatus.READY: "ready",
            CapabilityStatus.DEGRADED: "capability_degraded",
            CapabilityStatus.APPROVAL_REQUIRED: "approval_required",
            CapabilityStatus.PERMISSION_REQUIRED: "permission_required",
            CapabilityStatus.AUTHENTICATION_REQUIRED: "authentication_required",
            CapabilityStatus.UNAVAILABLE: "capability_unavailable",
        }
        status = runtime.status
        return _decision(
            capability_id,
            status,
            reason_codes[status],
            runtime.explanation or f"Capability status is {status.value}.",
            approval_could_resolve=status
            in {
                CapabilityStatus.APPROVAL_REQUIRED,
                CapabilityStatus.PERMISSION_REQUIRED,
            },
        )


def _decision(
    capability_id: str,
    status: CapabilityStatus,
    reason_code: str,
    explanation: str,
    missing: tuple[str, ...] = (),
    *,
    approval_could_resolve: bool = False,
) -> CapabilityDecision:
    return CapabilityDecision(
        capability_id,
        status,
        reason_code,
        explanation,
        missing,
        approval_could_resolve,
    )


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _require_schema(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("serialized nested model must be an object")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed
