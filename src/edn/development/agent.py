"""Replaceable development-agent and validation boundaries."""

from __future__ import annotations

from typing import Protocol

from edn.development.models import AgentResult, DevelopmentTask, ValidationResult


class DevelopmentAgent(Protocol):
    def implement(self, task: DevelopmentTask, *, repair_cycle: int) -> AgentResult: ...


class DevelopmentValidator(Protocol):
    def validate(self, task: DevelopmentTask) -> ValidationResult: ...


class ManualLocalAgent:
    """Prepare work for a local Codex session without faking execution."""

    def implement(self, task: DevelopmentTask, *, repair_cycle: int) -> AgentResult:
        return AgentResult(
            False,
            (
                f"Manual/local agent execution required for {task.task_id}; "
                f"repair cycle {repair_cycle}."
            ),
            failure_signature="manual_agent_required",
        )
