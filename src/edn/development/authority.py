"""Fail-closed development standing-authority evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edn.development.models import (
    AuthorityDecision,
    AuthorityOutcome,
    DevelopmentTask,
    EscalationRequest,
)


@dataclass(frozen=True, slots=True)
class DevelopmentAuthorityPolicy:
    policy_id: str
    version: str
    allowed_actions: frozenset[str]
    owner_required_actions: frozenset[str]
    prohibited_actions: frozenset[str]
    git_checkpoint: GitCheckpointAuthority | None = None

    @classmethod
    def load(cls, path: Path) -> DevelopmentAuthorityPolicy:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("development authority policy must be an object")
        checkpoint = value.get("git_checkpoint_authority")
        return cls(
            str(value["policy_id"]),
            str(value["version"]),
            _set(value, "allowed_actions"),
            _set(value, "owner_required_actions"),
            _set(value, "prohibited_actions"),
            None
            if checkpoint is None
            else GitCheckpointAuthority.from_dict(_object(checkpoint)),
        )

    def evaluate(self, actions: tuple[str, ...]) -> AuthorityDecision:
        if not actions:
            return AuthorityDecision(
                AuthorityOutcome.INDETERMINATE,
                "authority_actions_missing",
                "Task declares no authority actions; unknown authority fails closed.",
                actions,
            )
        unknown = set(actions) - (
            self.allowed_actions | self.owner_required_actions | self.prohibited_actions
        )
        if unknown:
            return AuthorityDecision(
                AuthorityOutcome.INDETERMINATE,
                "authority_unknown",
                f"No standing rule exists for: {', '.join(sorted(unknown))}.",
                actions,
            )
        prohibited = set(actions) & self.prohibited_actions
        if prohibited:
            return AuthorityDecision(
                AuthorityOutcome.PROHIBITED,
                "action_prohibited",
                f"Policy prohibits: {', '.join(sorted(prohibited))}.",
                actions,
            )
        owner = set(actions) & self.owner_required_actions
        if owner:
            return AuthorityDecision(
                AuthorityOutcome.OWNER_REQUIRED,
                "owner_authority_required",
                f"Owner authority is required for: {', '.join(sorted(owner))}.",
                actions,
            )
        return AuthorityDecision(
            AuthorityOutcome.ALLOWED,
            "standing_authority",
            "All task actions are covered by development standing authority.",
            actions,
        )

    def escalation_for(
        self, task: DevelopmentTask, decision: AuthorityDecision
    ) -> EscalationRequest:
        return EscalationRequest(
            blocked=f"{task.task_id}: {task.objective}",
            authority_reason=decision.explanation,
            exact_request=(
                "Approve only the listed task actions and scope: "
                + ", ".join(decision.actions)
            ),
            if_approved="The task may proceed within the exact approved scope.",
            if_declined="The task remains blocked; other eligible tasks may continue.",
            minimum_authority=", ".join(decision.actions),
            reversible=not any("destructive" in item for item in decision.actions),
            recommendation="Approve only if the requested scope matches owner intent.",
        )

    def evaluate_git_checkpoint(
        self, request: GitCheckpointRequest
    ) -> AuthorityDecision:
        """Evaluate one exact stage/commit/push checkpoint; ambiguity fails closed."""
        actions = (
            "git.stage.validated_increment",
            "git.commit.validated_increment",
            "git.push.current_upstream",
        )
        authority = self.git_checkpoint
        if authority is None:
            return AuthorityDecision(
                AuthorityOutcome.INDETERMINATE,
                "git_checkpoint_policy_missing",
                "No standing Git checkpoint policy is configured.",
                actions,
            )
        prohibited = set(request.operations) & authority.prohibited_operations
        if prohibited:
            return AuthorityDecision(
                AuthorityOutcome.PROHIBITED,
                "git_operation_prohibited",
                f"Policy permanently prohibits: {', '.join(sorted(prohibited))}.",
                actions,
            )
        branch_protected = request.branch in authority.protected_branches or any(
            request.branch.startswith(prefix)
            for prefix in authority.protected_branch_prefixes
        )
        branch_allowed = any(
            request.branch.startswith(prefix)
            for prefix in authority.allowed_branch_prefixes
        )
        if branch_protected or not branch_allowed:
            return _checkpoint_denied(
                "git_branch_not_authorised",
                "Checkpoint branch is protected or is not an allowed feature branch.",
                actions,
            )
        if (
            request.upstream_remote != authority.allowed_remote
            or request.target_remote != request.upstream_remote
            or request.upstream_branch != request.branch
            or request.target_branch != request.branch
        ):
            return _checkpoint_denied(
                "git_upstream_mismatch",
                "Push target must be the current branch's existing exact upstream.",
                actions,
            )
        required = {
            "completed_reviewed_increment": request.completed_reviewed_increment,
            "increment_only_changes": request.increment_only_changes,
            "validation_passed": request.validation_passed,
            "commit_message_matches_increment": (
                request.commit_message_matches_increment
            ),
            "hooks_and_validation_enabled": request.hooks_and_validation_enabled,
            "contains_no_secrets_protected_data_or_live_evidence": (
                request.contains_no_secrets_protected_data_or_live_evidence
            ),
            "audit_state_recording_planned": request.audit_state_recording_planned,
            "verify_head_equals_upstream_after_push": (
                request.verify_head_equals_upstream_after_push
            ),
        }
        missing = sorted(name for name, enabled in required.items() if not enabled)
        if missing:
            return _checkpoint_denied(
                "git_checkpoint_precondition_failed",
                "Checkpoint preconditions failed: " + ", ".join(missing) + ".",
                actions,
            )
        return AuthorityDecision(
            AuthorityOutcome.ALLOWED,
            "validated_feature_checkpoint",
            "Validated increment may be staged, committed, pushed to its "
            "existing upstream, and verified.",
            actions,
        )


@dataclass(frozen=True, slots=True)
class GitCheckpointAuthority:
    allowed_branch_prefixes: tuple[str, ...]
    protected_branches: frozenset[str]
    protected_branch_prefixes: tuple[str, ...]
    allowed_remote: str
    prohibited_operations: frozenset[str]
    required_record_fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GitCheckpointAuthority:
        return cls(
            _tuple(value, "allowed_branch_prefixes"),
            _set(value, "protected_branches"),
            _tuple(value, "protected_branch_prefixes"),
            str(value["allowed_remote"]),
            _set(value, "prohibited_operations"),
            _tuple(value, "required_record_fields"),
        )


@dataclass(frozen=True, slots=True)
class GitCheckpointRequest:
    branch: str
    upstream_remote: str
    upstream_branch: str
    target_remote: str
    target_branch: str
    operations: tuple[str, ...]
    completed_reviewed_increment: bool
    increment_only_changes: bool
    validation_passed: bool
    commit_message_matches_increment: bool
    hooks_and_validation_enabled: bool
    contains_no_secrets_protected_data_or_live_evidence: bool
    audit_state_recording_planned: bool
    verify_head_equals_upstream_after_push: bool


def _checkpoint_denied(
    reason_code: str, explanation: str, actions: tuple[str, ...]
) -> AuthorityDecision:
    return AuthorityDecision(
        AuthorityOutcome.PROHIBITED, reason_code, explanation, actions
    )


def _set(value: dict[str, Any], key: str) -> frozenset[str]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{key} must be a list of strings")
    return frozenset(raw)


def _tuple(value: dict[str, Any], key: str) -> tuple[str, ...]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(raw)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("git_checkpoint_authority must be an object")
    return value
