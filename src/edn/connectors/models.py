"""Immutable connector manifests and lifecycle envelopes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self
from urllib.parse import parse_qsl, urlsplit

from edn.core import (
    CapabilityManifest,
    CapabilityUseDecision,
    Classification,
    EvidenceRef,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    UniversalRecordRef,
)
from edn.core.security import SCHEMA_VERSION, validate_identifier

CONNECTOR_MANIFEST_SCHEMA_VERSION = "1.0.0"
CONNECTOR_OPERATIONS = frozenset(
    {
        "discover",
        "inspect",
        "plan",
        "authenticate",
        "ingest",
        "sync",
        "checkpoint",
        "resume",
        "verify",
        "search",
        "act",
    }
)
_SECRET_KEYS = frozenset(
    {"password", "secret", "token", "access_token", "refresh_token", "api_key"}
)


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    connector_id: str
    version: str
    display_name: str
    provider_id: str
    description: str
    connector_type: str
    capabilities: tuple[CapabilityManifest, ...]
    supported_operations: frozenset[str]
    configuration_schema_ref: str
    configuration_schema_version: str
    dependencies: frozenset[str] = frozenset()
    minimum_core_version: str = "1.0.0"
    manifest_schema_version: str = CONNECTOR_MANIFEST_SCHEMA_VERSION
    manifest_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "connector_id",
            "version",
            "provider_id",
            "connector_type",
            "configuration_schema_version",
            "minimum_core_version",
            "manifest_schema_version",
        ):
            validate_identifier(getattr(self, name), name)
        for name in ("display_name", "description", "configuration_schema_ref"):
            value = getattr(self, name)
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        _validate_safe_uri(self.configuration_schema_ref, "configuration_schema_ref")
        if self.manifest_schema_version != CONNECTOR_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported connector manifest schema version")
        if not self.capabilities:
            raise ValueError("connector must declare at least one capability")
        object.__setattr__(
            self,
            "capabilities",
            tuple(sorted(self.capabilities, key=lambda item: item.capability_id)),
        )
        capability_ids = [item.capability_id for item in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("connector capability IDs must be unique")
        if any(item.connector_id != self.connector_id for item in self.capabilities):
            raise ValueError(
                "capability connector_id does not match connector manifest"
            )
        if (
            not self.supported_operations
            or not self.supported_operations <= CONNECTOR_OPERATIONS
        ):
            raise ValueError("supported_operations contains an unknown operation")
        declared = frozenset(
            operation
            for capability in self.capabilities
            for operation in capability.operations
        )
        if declared != self.supported_operations:
            raise ValueError("connector and capability operation declarations differ")
        for dependency in self.dependencies:
            validate_identifier(dependency, "dependencies")
        object.__setattr__(self, "manifest_hash", self._calculate_hash())

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "manifest_schema_version": self.manifest_schema_version,
            "connector_id": self.connector_id,
            "version": self.version,
            "display_name": self.display_name,
            "provider_id": self.provider_id,
            "description": self.description,
            "connector_type": self.connector_type,
            "capabilities": [
                item.to_dict()
                for item in sorted(
                    self.capabilities, key=lambda item: item.capability_id
                )
            ],
            "supported_operations": sorted(self.supported_operations),
            "configuration_schema_ref": self.configuration_schema_ref,
            "configuration_schema_version": self.configuration_schema_version,
            "dependencies": sorted(self.dependencies),
            "minimum_core_version": self.minimum_core_version,
        }

    def _calculate_hash(self) -> str:
        return hashlib.sha256(_stable_json(self._content_dict()).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self._content_dict(), "manifest_hash": self.manifest_hash}

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be a list")
        instance = cls(
            connector_id=str(value["connector_id"]),
            version=str(value["version"]),
            display_name=str(value["display_name"]),
            provider_id=str(value["provider_id"]),
            description=str(value["description"]),
            connector_type=str(value["connector_type"]),
            capabilities=tuple(
                CapabilityManifest.from_dict(_dict(item)) for item in capabilities
            ),
            supported_operations=_string_set(
                value.get("supported_operations"), "supported_operations"
            ),
            configuration_schema_ref=str(value["configuration_schema_ref"]),
            configuration_schema_version=str(value["configuration_schema_version"]),
            dependencies=_string_set(value.get("dependencies"), "dependencies"),
            minimum_core_version=str(value["minimum_core_version"]),
            manifest_schema_version=str(value["manifest_schema_version"]),
        )
        if value.get("manifest_hash") != instance.manifest_hash:
            raise ValueError("connector manifest hash does not match content")
        return instance


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    request_id: str
    correlation_id: str
    principal: PrincipalContext
    purpose: Purpose
    security_domain: SecurityDomain
    classification: Classification
    capability_id: str
    operation: str
    authority: CapabilityUseDecision
    scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("request_id", "correlation_id", "capability_id", "operation"):
            validate_identifier(getattr(self, name), name)
        for item in self.scope:
            validate_identifier(item, "scope")
        request = self.authority.request
        if not self.authority.is_usable:
            raise ValueError(
                "connector request requires an explicitly usable authority decision"
            )
        if (
            request.principal != self.principal
            or request.purpose != self.purpose
            or request.security_domain != self.security_domain
            or request.classification != self.classification
            or request.capability_id != self.capability_id
            or request.operation != self.operation
            or request.resource_scope != self.scope
        ):
            raise ValueError(
                "authority decision is not bound to this connector request"
            )


@dataclass(frozen=True, slots=True)
class ResourceCandidate:
    resource_id: str
    resource_type: str
    source_ref: str
    security_domain: SecurityDomain
    classification: Classification
    size_bytes: int | None = None
    modified_at: datetime | None = None
    estimated_relevance: str = "unknown"
    already_known: bool | None = None
    required_permissions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.resource_id, "resource_id")
        validate_identifier(self.resource_type, "resource_type")
        if not self.source_ref.strip():
            raise ValueError("source_ref must not be blank")
        _validate_safe_uri(self.source_ref, "source_ref")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if self.modified_at is not None and self.modified_at.tzinfo is None:
            raise ValueError("modified_at must be timezone-aware")
        validate_identifier(self.estimated_relevance, "estimated_relevance")
        for permission in self.required_permissions:
            validate_identifier(permission, "required_permissions")
        for warning in self.warnings:
            if not warning.strip():
                raise ValueError("warnings must not contain blank values")


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    request_id: str
    resources: tuple[ResourceCandidate, ...]
    warnings: tuple[str, ...] = ()
    checkpoint: Checkpoint | None = None
    processed_resources: int = 0
    complete: bool = True

    def __post_init__(self) -> None:
        if self.processed_resources < 0:
            raise ValueError("processed_resources must not be negative")
        if not self.complete and self.checkpoint is None:
            raise ValueError("incomplete discovery requires a durable checkpoint")


@dataclass(frozen=True, slots=True)
class InspectionResult:
    request_id: str
    resource: ResourceCandidate
    observations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConnectorPlan:
    plan_id: str
    connector_id: str
    connector_version: str
    capability_id: str
    operation: str
    scope: tuple[str, ...]
    permissions_required: tuple[str, ...]
    proposed_mutations: tuple[str, ...]
    risk_level: str
    irreversible_effects: tuple[str, ...]
    approval_required: bool
    estimated_items: int | None = None
    estimated_storage_bytes: int | None = None
    configuration_hash: str | None = None
    plan_hash: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "plan_id",
            "connector_id",
            "connector_version",
            "capability_id",
            "operation",
            "risk_level",
        ):
            validate_identifier(getattr(self, name), name)
        for name in ("scope", "permissions_required"):
            for value in getattr(self, name):
                validate_identifier(value, name)
        if self.estimated_items is not None and self.estimated_items < 0:
            raise ValueError("estimated_items must not be negative")
        if (
            self.estimated_storage_bytes is not None
            and self.estimated_storage_bytes < 0
        ):
            raise ValueError("estimated_storage_bytes must not be negative")
        if self.configuration_hash is not None and not _is_sha256(
            self.configuration_hash
        ):
            raise ValueError("configuration_hash must be a lowercase SHA-256 value")
        object.__setattr__(self, "plan_hash", self._calculate_hash())

    def _content_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "connector_id": self.connector_id,
            "connector_version": self.connector_version,
            "capability_id": self.capability_id,
            "operation": self.operation,
            "scope": list(self.scope),
            "permissions_required": list(self.permissions_required),
            "proposed_mutations": list(self.proposed_mutations),
            "risk_level": self.risk_level,
            "irreversible_effects": list(self.irreversible_effects),
            "approval_required": self.approval_required,
            "estimated_items": self.estimated_items,
            "estimated_storage_bytes": self.estimated_storage_bytes,
            "configuration_hash": self.configuration_hash,
        }

    def _calculate_hash(self) -> str:
        return hashlib.sha256(_stable_json(self._content_dict()).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self._content_dict(), "plan_hash": self.plan_hash}

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        instance = cls(
            plan_id=str(value["plan_id"]),
            connector_id=str(value["connector_id"]),
            connector_version=str(value["connector_version"]),
            capability_id=str(value["capability_id"]),
            operation=str(value["operation"]),
            scope=_string_tuple(value.get("scope"), "scope"),
            permissions_required=_string_tuple(
                value.get("permissions_required"), "permissions_required"
            ),
            proposed_mutations=_string_tuple(
                value.get("proposed_mutations"), "proposed_mutations", validate=False
            ),
            risk_level=str(value["risk_level"]),
            irreversible_effects=_string_tuple(
                value.get("irreversible_effects"),
                "irreversible_effects",
                validate=False,
            ),
            approval_required=_strict_bool(value.get("approval_required")),
            estimated_items=_optional_int(value.get("estimated_items")),
            estimated_storage_bytes=_optional_int(value.get("estimated_storage_bytes")),
            configuration_hash=_optional_str(value.get("configuration_hash")),
        )
        if value.get("plan_hash") != instance.plan_hash:
            raise ValueError("connector plan hash does not match content")
        return instance


@dataclass(frozen=True, slots=True)
class Checkpoint:
    checkpoint_id: str
    connector_id: str
    connector_version: str
    configuration_hash: str
    operation: str
    source_scope: tuple[str, ...]
    resume_marker: str
    durable_items: int
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("checkpoint_id", "connector_id", "connector_version", "operation"):
            validate_identifier(getattr(self, name), name)
        if not _is_sha256(self.configuration_hash):
            raise ValueError("configuration_hash must be a lowercase SHA-256 value")
        for value in self.source_scope:
            validate_identifier(value, "source_scope")
        validate_identifier(self.resume_marker, "resume_marker")
        if self.durable_items < 0:
            raise ValueError("durable_items must not be negative")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    def is_compatible(
        self, *, connector_id: str, connector_version: str, configuration_hash: str
    ) -> bool:
        return (
            self.connector_id == connector_id
            and self.connector_version == connector_version
            and self.configuration_hash == configuration_hash
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "connector_id": self.connector_id,
            "connector_version": self.connector_version,
            "configuration_hash": self.configuration_hash,
            "operation": self.operation,
            "source_scope": list(self.source_scope),
            "resume_marker": self.resume_marker,
            "durable_items": self.durable_items,
            "created_at": _format_datetime(self.created_at),
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        created_at = _parse_datetime(value.get("created_at"))
        if created_at is None:
            raise ValueError("created_at is required")
        return cls(
            str(value["checkpoint_id"]),
            str(value["connector_id"]),
            str(value["connector_version"]),
            str(value["configuration_hash"]),
            str(value["operation"]),
            _string_tuple(value.get("source_scope"), "source_scope"),
            str(value["resume_marker"]),
            int(value["durable_items"]),
            created_at,
        )


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    VERIFIED_WITH_WARNINGS = "verified_with_warnings"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    operation_id: str
    status: VerificationStatus
    explanation: str
    expected_count: int | None = None
    actual_count: int | None = None
    warnings: tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        return self.status in {
            VerificationStatus.VERIFIED,
            VerificationStatus.VERIFIED_WITH_WARNINGS,
        }


@dataclass(frozen=True, slots=True)
class IngestResult:
    request_id: str
    records: tuple[UniversalRecordRef, ...]
    checkpoint: Checkpoint | None = None
    processed_items: int = 0
    total_items: int | None = None
    complete: bool = True

    def __post_init__(self) -> None:
        if self.processed_items < 0:
            raise ValueError("processed_items must not be negative")
        if self.total_items is not None and self.total_items < self.processed_items:
            raise ValueError("total_items must not be less than processed_items")
        if not self.complete and self.checkpoint is None:
            raise ValueError("incomplete ingestion requires a durable checkpoint")


@dataclass(frozen=True, slots=True)
class SearchResult:
    request_id: str
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class ActionResult:
    request_id: str
    plan_id: str
    plan_hash: str
    changed_items: int
    verification: VerificationResult


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _require_schema(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("nested value must be an object")
    return value


def _string_set(value: object, field_name: str) -> frozenset[str]:
    return frozenset(_string_tuple(value, field_name))


def _string_tuple(
    value: object, field_name: str, *, validate: bool = True
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    result = tuple(value)
    if validate:
        for item in result:
            validate_identifier(item, field_name)
    elif any(not item.strip() for item in result):
        raise ValueError(f"{field_name} must not contain blanks")
    return result


def _strict_bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("value must be a boolean")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("value must be an integer")
    return value


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


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_safe_uri(value: str, field_name: str) -> None:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain credentials")
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if query_keys & _SECRET_KEYS:
        raise ValueError(f"{field_name} must not contain secret query parameters")
