"""Immutable capability declaration and availability contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from edn.core.security import SCHEMA_VERSION, validate_identifier


class CapabilityStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PERMISSION_REQUIRED = "permission_required"
    APPROVAL_REQUIRED = "approval_required"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    capability_id: str
    provider_id: str
    connector_id: str
    version: str
    operations: frozenset[str]
    required_permissions: frozenset[str]
    supported_domain_scopes: frozenset[str]
    risk_level: str
    dependencies: frozenset[str] = frozenset()
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "capability_id",
            "provider_id",
            "connector_id",
            "version",
            "risk_level",
        ):
            validate_identifier(getattr(self, name), name)
        for name, values in (
            ("operations", self.operations),
            ("required_permissions", self.required_permissions),
            ("supported_domain_scopes", self.supported_domain_scopes),
            ("dependencies", self.dependencies),
        ):
            if name in {"operations", "supported_domain_scopes"} and not values:
                raise ValueError(f"{name} must not be empty")
            for value in values:
                validate_identifier(value, name)
        if self.manifest_hash is not None and not _is_sha256(self.manifest_hash):
            raise ValueError("manifest_hash must be a lowercase SHA-256 value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "connector_id": self.connector_id,
            "version": self.version,
            "operations": sorted(self.operations),
            "required_permissions": sorted(self.required_permissions),
            "supported_domain_scopes": sorted(self.supported_domain_scopes),
            "risk_level": self.risk_level,
            "dependencies": sorted(self.dependencies),
            "manifest_hash": self.manifest_hash,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            capability_id=str(value["capability_id"]),
            provider_id=str(value["provider_id"]),
            connector_id=str(value["connector_id"]),
            version=str(value["version"]),
            operations=_string_set(value.get("operations"), "operations"),
            required_permissions=_string_set(
                value.get("required_permissions"), "required_permissions"
            ),
            supported_domain_scopes=_string_set(
                value.get("supported_domain_scopes"), "supported_domain_scopes"
            ),
            risk_level=str(value["risk_level"]),
            dependencies=_string_set(value.get("dependencies", []), "dependencies"),
            manifest_hash=_optional_str(value.get("manifest_hash")),
        )


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    capability_id: str
    status: CapabilityStatus
    reason_code: str
    explanation: str
    missing_requirements: tuple[str, ...] = ()
    approval_could_resolve: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.capability_id, "capability_id")
        validate_identifier(self.reason_code, "reason_code")
        if not self.explanation.strip():
            raise ValueError("explanation must not be blank")
        for requirement in self.missing_requirements:
            validate_identifier(requirement, "missing_requirements")
        if self.approval_could_resolve and self.status not in {
            CapabilityStatus.APPROVAL_REQUIRED,
            CapabilityStatus.PERMISSION_REQUIRED,
        }:
            raise ValueError("approval cannot resolve this capability status")

    @property
    def is_usable(self) -> bool:
        return self.status is CapabilityStatus.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "capability_id": self.capability_id,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "missing_requirements": list(self.missing_requirements),
            "approval_could_resolve": self.approval_could_resolve,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        missing = value.get("missing_requirements")
        if not isinstance(missing, list) or not all(
            isinstance(item, str) for item in missing
        ):
            raise ValueError("missing_requirements must be a list of strings")
        approval = value.get("approval_could_resolve")
        if not isinstance(approval, bool):
            raise ValueError("approval_could_resolve must be a boolean")
        return cls(
            capability_id=str(value["capability_id"]),
            status=CapabilityStatus(value["status"]),
            reason_code=str(value["reason_code"]),
            explanation=str(value["explanation"]),
            missing_requirements=tuple(missing),
            approval_could_resolve=approval,
        )


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _require_schema(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")


def _string_set(value: object, field_name: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return frozenset(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
