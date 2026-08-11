"""Machine-readable roadmap loading and deterministic task selection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from edn.development.authority import DevelopmentAuthorityPolicy
from edn.development.models import (
    AuthorityOutcome,
    DevelopmentState,
    DevelopmentTask,
    DevelopmentTaskStatus,
)


@dataclass(frozen=True, slots=True)
class DevelopmentRoadmap:
    roadmap_id: str
    version: str
    tasks: tuple[DevelopmentTask, ...]

    @classmethod
    def load(cls, path: Path) -> DevelopmentRoadmap:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("tasks"), list):
            raise ValueError("development roadmap must contain a task list")
        roadmap = cls(
            str(value["roadmap_id"]),
            str(value["version"]),
            tuple(DevelopmentTask.from_dict(item) for item in value["tasks"]),
        )
        identifiers = [item.task_id for item in roadmap.tasks]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("roadmap task IDs must be unique")
        known = set(identifiers)
        if any(
            prerequisite not in known
            for task in roadmap.tasks
            for prerequisite in task.prerequisites
        ):
            raise ValueError("roadmap contains an unknown prerequisite")
        return roadmap

    def task(self, task_id: str) -> DevelopmentTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise KeyError(task_id)

    def select_next(
        self,
        state: DevelopmentState,
        policy: DevelopmentAuthorityPolicy,
        *,
        excluded: frozenset[str] = frozenset(),
    ) -> DevelopmentTask | None:
        completed = set(state.completed_increments)
        preferred = state.next_recommended_increment
        candidates = sorted(
            (
                task
                for task in self.tasks
                if task.status is DevelopmentTaskStatus.PENDING
                and task.task_id not in excluded
                and set(task.prerequisites) <= completed
            ),
            key=lambda item: (item.task_id != preferred, item.task_id),
        )
        for task in candidates:
            decision = policy.evaluate(task.authority_actions)
            if decision.outcome is AuthorityOutcome.ALLOWED:
                return task
        return None

    def eligible_tasks(
        self,
        state: DevelopmentState,
        *,
        excluded: frozenset[str] = frozenset(),
    ) -> tuple[DevelopmentTask, ...]:
        completed = set(state.completed_increments)
        preferred = state.next_recommended_increment
        return tuple(
            sorted(
                (
                    task
                    for task in self.tasks
                    if task.status is DevelopmentTaskStatus.PENDING
                    and task.task_id not in excluded
                    and set(task.prerequisites) <= completed
                ),
                key=lambda item: (item.task_id != preferred, item.task_id),
            )
        )
