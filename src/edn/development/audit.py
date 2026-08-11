"""Content-free JSONL development audit events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from edn.development.models import AuditEvent


class DevelopmentAuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class JsonlDevelopmentAudit:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")


class InMemoryDevelopmentAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)
