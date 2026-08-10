"""Configuration-driven permission policy evaluation and safe composition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from edn.core.capabilities import CapabilityDecision, CapabilityStatus
from edn.core.permissions import (
    PermissionDecision,
    PermissionOutcome,
    PermissionRequest,
)
from edn.core.registry import CapabilityRegistry
from edn.core.security import (
    SCHEMA_VERSION,
    Classification,
    PrincipalContext,
    Purpose,
    SecurityDomain,
    validate_identifier,
)


@dataclass(frozen=True, slots=True)
class PolicyRule:
    rule_id: str
    outcome: PermissionOutcome
    reason: str
    principal_ids: frozenset[str] = frozenset()
    principal_kinds: frozenset[str] = frozenset()
    tenant_ids: frozenset[str] = frozenset()
    domain_ids: frozenset[str] = frozenset()
    classification_schemes: frozenset[str] = frozenset()
    classification_levels: frozenset[str] = frozenset()
    purpose_ids: frozenset[str] = frozenset()
    capability_ids: frozenset[str] = frozenset()
    operations: frozenset[str] = frozenset()
    resource_scopes: frozenset[str] = frozenset()
    expires_at: datetime | None = None
    approver_id: str | None = None
    approval_ref: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.rule_id, "rule_id")
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        for name in _SELECTOR_FIELDS:
            for value in getattr(self, name):
                validate_identifier(value, name)
        for name in ("approver_id", "approval_ref"):
            value = getattr(self, name)
            if value is not None:
                validate_identifier(value, name)
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        if self.outcome is PermissionOutcome.TEMPORARILY_ALLOWED:
            if self.expires_at is None or self.approval_ref is None:
                raise ValueError(
                    "temporary policy requires expiry and approval reference"
                )
        elif self.expires_at is not None:
            raise ValueError("expiry is only valid for temporary authority")
        if (
            self.outcome is PermissionOutcome.ALLOWED_WITHIN_SCOPE
            and not self.resource_scopes
        ):
            raise ValueError("scoped policy requires resource scopes")

    @property
    def specificity(self) -> int:
        return sum(bool(getattr(self, field)) for field in _SELECTOR_FIELDS)

    def matches(self, request: PermissionRequest) -> bool:
        values = {
            "principal_ids": request.principal.principal_id,
            "principal_kinds": request.principal.principal_kind,
            "tenant_ids": request.principal.tenant_id,
            "domain_ids": request.security_domain.domain_id,
            "classification_schemes": request.classification.scheme_id,
            "classification_levels": request.classification.level_id,
            "purpose_ids": request.purpose.purpose_id,
            "capability_ids": request.capability_id,
            "operations": request.operation,
        }
        if any(
            selector and values[name] not in selector
            for name, selector in ((name, getattr(self, name)) for name in values)
        ):
            return False
        if self.resource_scopes:
            return bool(request.resource_scope) and set(request.resource_scope) <= set(
                self.resource_scopes
            )
        return True

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "rule_id": self.rule_id,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "expires_at": _format_datetime(self.expires_at),
            "approver_id": self.approver_id,
            "approval_ref": self.approval_ref,
        }
        value.update({name: sorted(getattr(self, name)) for name in _SELECTOR_FIELDS})
        return value

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        selectors = {
            name: _string_set(value.get(name), name) for name in _SELECTOR_FIELDS
        }
        return cls(
            rule_id=str(value["rule_id"]),
            outcome=PermissionOutcome(value["outcome"]),
            reason=str(value["reason"]),
            **selectors,
            expires_at=_parse_datetime(value.get("expires_at")),
            approver_id=_optional_str(value.get("approver_id")),
            approval_ref=_optional_str(value.get("approval_ref")),
        )


@dataclass(frozen=True, slots=True)
class PolicySet:
    policy_id: str
    version: str
    rules: tuple[PolicyRule, ...]

    def __post_init__(self) -> None:
        validate_identifier(self.policy_id, "policy_id")
        validate_identifier(self.version, "version")
        identifiers = [rule.rule_id for rule in self.rules]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("policy rule IDs must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "version": self.version,
            "rules": [rule.to_dict() for rule in sorted(self.rules, key=_rule_id)],
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        rules = value.get("rules")
        if not isinstance(rules, list):
            raise ValueError("rules must be a list")
        return cls(
            str(value["policy_id"]),
            str(value["version"]),
            tuple(PolicyRule.from_dict(_dict(rule)) for rule in rules),
        )


class PermissionEvaluator:
    def __init__(self, policy_set: PolicySet) -> None:
        self._policy_set = policy_set

    def evaluate(
        self, request: PermissionRequest | None, *, now: datetime
    ) -> PermissionDecision:
        if request is None:
            return PermissionDecision(
                "unknown-request",
                PermissionOutcome.INDETERMINATE,
                "Principal and request context are required.",
                self._policy_set.policy_id,
            )
        if now.tzinfo is None:
            raise ValueError("evaluation time must be timezone-aware")
        if not request.principal.allows_domain(request.security_domain):
            return PermissionDecision(
                request.request_id,
                PermissionOutcome.PROHIBITED,
                "The requested security domain is not active for this principal.",
                "security_domain_not_active",
            )
        matches = tuple(
            rule for rule in self._policy_set.rules if rule.matches(request)
        )
        prohibitions = tuple(
            rule for rule in matches if rule.outcome is PermissionOutcome.PROHIBITED
        )
        if prohibitions:
            selected = sorted(
                prohibitions, key=lambda rule: (-rule.specificity, rule.rule_id)
            )[0]
            return _rule_decision(request, selected)
        if not matches:
            return PermissionDecision(
                request.request_id,
                PermissionOutcome.INDETERMINATE,
                "No policy rule matched the request.",
                self._policy_set.policy_id,
            )
        highest = max(rule.specificity for rule in matches)
        finalists = tuple(rule for rule in matches if rule.specificity == highest)
        signatures = {
            (rule.outcome, rule.resource_scopes, rule.expires_at, rule.approval_ref)
            for rule in finalists
        }
        if len(signatures) != 1:
            return PermissionDecision(
                request.request_id,
                PermissionOutcome.INDETERMINATE,
                "Equally specific policy rules conflict.",
                self._policy_set.policy_id,
            )
        selected = sorted(finalists, key=_rule_id)[0]
        if (
            selected.outcome is PermissionOutcome.TEMPORARILY_ALLOWED
            and selected.expires_at is not None
            and now >= selected.expires_at
        ):
            return PermissionDecision(
                request.request_id,
                PermissionOutcome.INDETERMINATE,
                "Temporary authority has expired.",
                selected.rule_id,
            )
        return _rule_decision(request, selected)


class UseDecisionOutcome(StrEnum):
    READY = "ready"
    APPROVAL_REQUIRED = "approval_required"
    PROHIBITED = "prohibited"
    UNAVAILABLE = "unavailable"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PERMISSION_REQUIRED = "permission_required"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class CapabilityUseDecision:
    request: PermissionRequest
    capability: CapabilityDecision
    permission: PermissionDecision
    outcome: UseDecisionOutcome
    reason_code: str
    explanation: str
    evaluated_at: datetime

    def __post_init__(self) -> None:
        validate_identifier(self.reason_code, "reason_code")
        if not self.explanation.strip():
            raise ValueError("explanation must not be blank")
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")

    @property
    def is_usable(self) -> bool:
        return self.outcome is UseDecisionOutcome.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request": self.request.to_dict(),
            "capability": self.capability.to_dict(),
            "permission": self.permission.to_dict(),
            "outcome": self.outcome.value,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "evaluated_at": _format_datetime(self.evaluated_at),
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        evaluated_at = _parse_datetime(value.get("evaluated_at"))
        if evaluated_at is None:
            raise ValueError("evaluated_at is required")
        return cls(
            request=PermissionRequest.from_dict(_dict(value["request"])),
            capability=CapabilityDecision.from_dict(_dict(value["capability"])),
            permission=PermissionDecision.from_dict(_dict(value["permission"])),
            outcome=UseDecisionOutcome(value["outcome"]),
            reason_code=str(value["reason_code"]),
            explanation=str(value["explanation"]),
            evaluated_at=evaluated_at,
        )


def evaluate_capability_use(
    registry: CapabilityRegistry,
    evaluator: PermissionEvaluator,
    request: PermissionRequest,
    *,
    now: datetime,
) -> CapabilityUseDecision:
    capability = registry.resolve(
        request.capability_id, request.operation, request.security_domain
    )
    permission = evaluator.evaluate(request, now=now)
    if permission.outcome is PermissionOutcome.PROHIBITED:
        outcome = UseDecisionOutcome.PROHIBITED
        code = "permission_prohibited"
        explanation = permission.reason
    elif not capability.is_usable:
        outcome = _CAPABILITY_OUTCOMES[capability.status]
        code = capability.reason_code
        explanation = capability.explanation
    elif permission.outcome is PermissionOutcome.APPROVAL_REQUIRED:
        outcome = UseDecisionOutcome.APPROVAL_REQUIRED
        code = "approval_required"
        explanation = permission.reason
    elif permission.is_allowed(at=now):
        outcome = UseDecisionOutcome.READY
        code = "ready"
        explanation = permission.reason
    else:
        outcome = UseDecisionOutcome.INDETERMINATE
        code = "permission_indeterminate"
        explanation = permission.reason
    return CapabilityUseDecision(
        request, capability, permission, outcome, code, explanation, now
    )


def evaluate_operation_candidates(
    registry: CapabilityRegistry,
    evaluator: PermissionEvaluator,
    principal: PrincipalContext,
    purpose: Purpose,
    security_domain: SecurityDomain,
    classification: Classification,
    operation: str,
    *,
    resource_scope: tuple[str, ...] = (),
    now: datetime,
) -> tuple[CapabilityUseDecision, ...]:
    """Evaluate exact operation candidates in deterministic capability-ID order."""
    validate_identifier(operation, "operation")
    decisions = []
    for candidate in registry.list(operation=operation):
        capability_id = candidate.manifest.capability_id
        request = PermissionRequest(
            f"query:{capability_id}",
            principal,
            purpose,
            capability_id,
            operation,
            security_domain,
            classification,
            resource_scope,
        )
        decisions.append(evaluate_capability_use(registry, evaluator, request, now=now))
    return tuple(decisions)


_SELECTOR_FIELDS = (
    "principal_ids",
    "principal_kinds",
    "tenant_ids",
    "domain_ids",
    "classification_schemes",
    "classification_levels",
    "purpose_ids",
    "capability_ids",
    "operations",
    "resource_scopes",
)
_CAPABILITY_OUTCOMES = {
    CapabilityStatus.READY: UseDecisionOutcome.READY,
    CapabilityStatus.APPROVAL_REQUIRED: UseDecisionOutcome.APPROVAL_REQUIRED,
    CapabilityStatus.UNAVAILABLE: UseDecisionOutcome.UNAVAILABLE,
    CapabilityStatus.AUTHENTICATION_REQUIRED: (
        UseDecisionOutcome.AUTHENTICATION_REQUIRED
    ),
    CapabilityStatus.PERMISSION_REQUIRED: UseDecisionOutcome.PERMISSION_REQUIRED,
    CapabilityStatus.DEGRADED: UseDecisionOutcome.DEGRADED,
    CapabilityStatus.DISABLED: UseDecisionOutcome.DISABLED,
    CapabilityStatus.INDETERMINATE: UseDecisionOutcome.INDETERMINATE,
}


def _rule_id(rule: PolicyRule) -> str:
    return rule.rule_id


def _rule_decision(request: PermissionRequest, rule: PolicyRule) -> PermissionDecision:
    scope = request.resource_scope if rule.resource_scopes else ()
    return PermissionDecision(
        request.request_id,
        rule.outcome,
        rule.reason,
        rule.rule_id,
        scope,
        rule.expires_at,
        rule.approver_id,
        rule.approval_ref,
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


def _string_set(value: object, field_name: str) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return frozenset(value)


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
