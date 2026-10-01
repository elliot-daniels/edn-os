"""Atomic JSON development state and repository reconstruction checks."""

from __future__ import annotations

import json
from pathlib import Path

from edn.development.models import DevelopmentState, RepositorySnapshot


class DevelopmentStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> DevelopmentState:
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("development state must be an object")
        return DevelopmentState.from_dict(value)

    def save(self, state: DevelopmentState) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def validate_repository(
    state: DevelopmentState, snapshot: RepositorySnapshot
) -> tuple[str, ...]:
    failures = []
    if snapshot.branch != state.current_branch:
        failures.append("unexpected_branch")
    unexpected = tuple(
        path
        for path in snapshot.dirty_paths
        if not any(
            path == expected or path.startswith(expected.rstrip("/") + "/")
            for expected in state.expected_dirty_paths
        )
    )
    if unexpected:
        failures.append("unexpected_dirty_paths:" + ",".join(unexpected))
    return tuple(failures)
