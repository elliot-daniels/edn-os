"""Immutable permission request and fail-closed decision contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from edn.core.security import (
    SCHEMA_VERSION,
    Classification,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    validate_identifier,
)


class PermissionOutcome(StrEnum):
    ALLOWED = "allowed"
    ALLOWED_WITHIN_SCOPE = "allowed_within_scope"
    APPROVAL_REQUIRED = "approval_required"
    TEMPORARILY_ALLOWED = "temporarily_allowed"
    PROHIBITED = "prohibited"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    request_id: str
    principal: PrincipalContext
    purpose: Purpose
    capability_id: str
    operation: str
    security_domain: SecurityDomain
    classification: Classification
    resource_scope: tuple[str, ...] = ()
    requested_duration_seconds: int | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.request_id, "request_id")
        validate_identifier(self.capability_id, "capability_id")
        validate_identifier(self.operation, "operation")
        if self.security_domain.tenant_id not in (None, self.principal.tenant_id):
            raise ValueError("requested domain belongs to another tenant")
        for scope in self.resource_scope:
            validate_identifier(scope, "resource_scope")
        if (
            self.requested_duration_seconds is not None
            and self.requested_duration_seconds <= 0
        ):
            raise ValueError("requested_duration_seconds must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "principal": self.principal.to_dict(),
            "purpose": self.purpose.to_dict(),
            "capability_id": self.capability_id,
            "operation": self.operation,
            "security_domain": self.security_domain.to_dict(),
            "classification": self.classification.to_dict(),
            "resource_scope": list(self.resource_scope),
            "requested_duration_seconds": self.requested_duration_seconds,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        scope = _string_tuple(value.get("resource_scope"), "resource_scope")
        duration = value.get("requested_duration_seconds")
        return cls(
            request_id=str(value["request_id"]),
            principal=PrincipalContext.from_dict(_dict(value["principal"])),
            purpose=Purpose.from_dict(_dict(value["purpose"])),
            capability_id=str(value["capability_id"]),
            operation=str(value["operation"]),
            security_domain=SecurityDomain.from_dict(_dict(value["security_domain"])),
            classification=Classification.from_dict(_dict(value["classification"])),
            resource_scope=scope,
            requested_duration_seconds=None if duration is None else int(duration),
        )


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    request_id: str
    outcome: PermissionOutcome
    reason: str
    policy_ref: str | None = None
    effective_scope: tuple[str, ...] = ()
    expires_at: datetime | None = None
    approver_id: str | None = None
    approval_ref: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.request_id, "request_id")
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        for name in ("policy_ref", "approver_id", "approval_ref"):
            value = getattr(self, name)
            if value is not None:
                validate_identifier(value, name)
        for scope in self.effective_scope:
            validate_identifier(scope, "effective_scope")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.outcome is PermissionOutcome.TEMPORARILY_ALLOWED:
            if self.expires_at is None or self.approval_ref is None:
                raise ValueError(
                    "temporary authority requires expiry and approval reference"
                )
        elif self.expires_at is not None:
            raise ValueError("expiry is only valid for temporary authority")
        if (
            self.outcome is PermissionOutcome.ALLOWED_WITHIN_SCOPE
            and not self.effective_scope
        ):
            raise ValueError("scoped authority requires an effective scope")

    def is_allowed(self, *, at: datetime | None = None) -> bool:
        if self.outcome in {
            PermissionOutcome.ALLOWED,
            PermissionOutcome.ALLOWED_WITHIN_SCOPE,
        }:
            return True
        if (
            self.outcome is not PermissionOutcome.TEMPORARILY_ALLOWED
            or self.expires_at is None
        ):
            return False
        moment = at or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("decision time must be timezone-aware")
        return moment < self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "policy_ref": self.policy_ref,
            "effective_scope": list(self.effective_scope),
            "expires_at": _format_datetime(self.expires_at),
            "approver_id": self.approver_id,
            "approval_ref": self.approval_ref,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            request_id=str(value["request_id"]),
            outcome=PermissionOutcome(value["outcome"]),
            reason=str(value["reason"]),
            policy_ref=_optional_str(value.get("policy_ref")),
            effective_scope=_string_tuple(
                value.get("effective_scope"), "effective_scope"
            ),
            expires_at=_parse_datetime(value.get("expires_at")),
            approver_id=_optional_str(value.get("approver_id")),
            approval_ref=_optional_str(value.get("approval_ref")),
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
        raise ValueError("expires_at must be an ISO 8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expires_at must be timezone-aware")
    return parsed
