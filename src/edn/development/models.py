"""Deterministic contracts for governed autonomous development."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from edn.core.security import validate_identifier


class DevelopmentTaskStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


class AuthorityOutcome(StrEnum):
    ALLOWED = "allowed"
    OWNER_REQUIRED = "owner_required"
    PROHIBITED = "prohibited"
    INDETERMINATE = "indeterminate"


class ReviewDisposition(StrEnum):
    PASS = "pass"
    REPAIR = "repair"
    OWNER_REQUIRED = "owner_required"


@dataclass(frozen=True, slots=True)
class DevelopmentTask:
    task_id: str
    objective: str
    prerequisites: tuple[str, ...]
    authority_actions: tuple[str, ...]
    risk: str
    expected_components: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    required_tests: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    dependencies: tuple[str, ...]
    status: DevelopmentTaskStatus
    successor_tasks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.task_id, "task_id")
        validate_identifier(self.risk, "risk")
        if not self.objective.strip() or not self.acceptance_criteria:
            raise ValueError("task objective and acceptance criteria are required")
        for values in (
            self.prerequisites,
            self.authority_actions,
            self.dependencies,
            self.successor_tasks,
        ):
            for value in values:
                validate_identifier(value, "task_reference")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DevelopmentTask:
        return cls(
            str(value["task_id"]),
            str(value["objective"]),
            _strings(value, "prerequisites"),
            _strings(value, "authority_actions"),
            str(value["risk"]),
            _strings(value, "expected_components"),
            _strings(value, "acceptance_criteria"),
            _strings(value, "required_tests"),
            _strings(value, "stop_conditions"),
            _strings(value, "dependencies"),
            DevelopmentTaskStatus(str(value["status"])),
            _strings(value, "successor_tasks"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "prerequisites": list(self.prerequisites),
            "authority_actions": list(self.authority_actions),
            "risk": self.risk,
            "expected_components": list(self.expected_components),
            "acceptance_criteria": list(self.acceptance_criteria),
            "required_tests": list(self.required_tests),
            "stop_conditions": list(self.stop_conditions),
            "dependencies": list(self.dependencies),
            "status": self.status.value,
            "successor_tasks": list(self.successor_tasks),
        }


@dataclass(frozen=True, slots=True)
class TestStatus:
    outcome: str
    commands: tuple[str, ...]
    passed: int | None
    failed: int | None
    validated_at: datetime

    def __post_init__(self) -> None:
        validate_identifier(self.outcome, "test_outcome")
        if self.validated_at.tzinfo is None:
            raise ValueError("validated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DevelopmentState:
    schema_version: str
    product: str
    version: str
    current_branch: str
    current_milestone: str
    completed_increments: tuple[str, ...]
    active_increment: str | None
    blocked_increments: tuple[tuple[str, str], ...]
    deferred_increments: tuple[str, ...]
    known_limitations: tuple[str, ...]
    test_status: TestStatus
    repository_status: str
    expected_dirty_paths: tuple[str, ...]
    last_validated_commit: str
    next_recommended_increment: str | None
    required_owner_decisions: tuple[str, ...]
    external_capability_blockers: tuple[str, ...]
    architecture_references: tuple[str, ...]
    updated_at: datetime
    provenance: str

    def __post_init__(self) -> None:
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        for value in self.completed_increments + self.deferred_increments:
            validate_identifier(value, "increment")
        if self.active_increment is not None:
            validate_identifier(self.active_increment, "active_increment")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DevelopmentState:
        raw_test = _object(value["test_status"])
        blocked = value.get("blocked_increments")
        if not isinstance(blocked, list):
            raise ValueError("blocked_increments must be a list")
        return cls(
            str(value["schema_version"]),
            str(value["product"]),
            str(value["version"]),
            str(value["current_branch"]),
            str(value["current_milestone"]),
            _strings(value, "completed_increments"),
            _optional(value.get("active_increment")),
            tuple((str(item["task_id"]), str(item["reason"])) for item in blocked),
            _strings(value, "deferred_increments"),
            _strings(value, "known_limitations"),
            TestStatus(
                str(raw_test["outcome"]),
                _strings(raw_test, "commands"),
                _optional_int(raw_test.get("passed")),
                _optional_int(raw_test.get("failed")),
                datetime.fromisoformat(str(raw_test["validated_at"])),
            ),
            str(value["repository_status"]),
            _strings(value, "expected_dirty_paths"),
            str(value["last_validated_commit"]),
            _optional(value.get("next_recommended_increment")),
            _strings(value, "required_owner_decisions"),
            _strings(value, "external_capability_blockers"),
            _strings(value, "architecture_references"),
            datetime.fromisoformat(str(value["updated_at"])),
            str(value["provenance"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "product": self.product,
            "version": self.version,
            "current_branch": self.current_branch,
            "current_milestone": self.current_milestone,
            "completed_increments": list(self.completed_increments),
            "active_increment": self.active_increment,
            "blocked_increments": [
                {"task_id": task_id, "reason": reason}
                for task_id, reason in self.blocked_increments
            ],
            "deferred_increments": list(self.deferred_increments),
            "known_limitations": list(self.known_limitations),
            "test_status": {
                "outcome": self.test_status.outcome,
                "commands": list(self.test_status.commands),
                "passed": self.test_status.passed,
                "failed": self.test_status.failed,
                "validated_at": self.test_status.validated_at.isoformat(),
            },
            "repository_status": self.repository_status,
            "expected_dirty_paths": list(self.expected_dirty_paths),
            "last_validated_commit": self.last_validated_commit,
            "next_recommended_increment": self.next_recommended_increment,
            "required_owner_decisions": list(self.required_owner_decisions),
            "external_capability_blockers": list(self.external_capability_blockers),
            "architecture_references": list(self.architecture_references),
            "updated_at": self.updated_at.isoformat(),
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    outcome: AuthorityOutcome
    reason_code: str
    explanation: str
    actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EscalationRequest:
    blocked: str
    authority_reason: str
    exact_request: str
    if_approved: str
    if_declined: str
    minimum_authority: str
    reversible: bool
    recommendation: str
    decision_options: tuple[str, ...] = ("GO", "NO-GO", "CONDITIONAL GO")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    failures: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    failure_signature: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    code: str
    explanation: str
    disposition: ReviewDisposition


@dataclass(frozen=True, slots=True)
class ReviewResult:
    findings: tuple[ReviewFinding, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.findings


@dataclass(frozen=True, slots=True)
class AgentResult:
    success: bool
    summary: str
    changed_paths: tuple[str, ...] = ()
    recommended_commit: str | None = None
    failure_signature: str | None = None


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    branch: str
    commit: str
    dirty_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_tasks: int = 1
    max_repair_cycles: int = 2
    max_elapsed_seconds: float = 1_800.0
    repeated_failure_limit: int = 2

    def __post_init__(self) -> None:
        if (
            min(
                self.max_tasks,
                self.max_repair_cycles,
                self.max_elapsed_seconds,
                self.repeated_failure_limit,
            )
            <= 0
        ):
            raise ValueError("run limits must be positive")


@dataclass(frozen=True, slots=True)
class RunReport:
    completed_tasks: tuple[str, ...]
    stopped_reason: str
    escalation: EscalationRequest | None = None
    prepared_commits: tuple[str, ...] = ()
    audit_events: int = 0


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    event_type: str
    timestamp: datetime
    task_id: str | None
    reason_code: str
    outcome: str
    evidence_refs: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str | int | bool | None], ...] = field(
        default_factory=tuple
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "reason_code": self.reason_code,
            "outcome": self.outcome,
            "evidence_refs": list(self.evidence_refs),
            "metadata": {key: value for key, value in self.metadata},
        }


def _strings(value: dict[str, Any], key: str) -> tuple[str, ...]:
    raw = value.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(raw)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("serialized value must be an object")
    return value


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("optional integer value must be an integer or null")
    return value
