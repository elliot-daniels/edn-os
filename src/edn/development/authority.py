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

    @classmethod
    def load(cls, path: Path) -> DevelopmentAuthorityPolicy:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("development authority policy must be an object")
        return cls(
            str(value["policy_id"]),
            str(value["version"]),
            _set(value, "allowed_actions"),
            _set(value, "owner_required_actions"),
            _set(value, "prohibited_actions"),
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


def _set(value: dict[str, Any], key: str) -> frozenset[str]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{key} must be a list of strings")
    return frozenset(raw)
