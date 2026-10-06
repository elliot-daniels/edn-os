"""Operations v1 Event contract; AI outputs never replace source content."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

EVENT_TYPES = frozenset(
    {
        "email",
        "job_request",
        "sms",
        "whatsapp",
        "call",
        "voicemail",
        "note",
        "job_update",
    }
)
DIRECTIONS = frozenset({"inbound", "outbound", "internal"})


def event_identity_key(source: str, source_account: str, external_id: str) -> str:
    """Versioned, exact source identity; never normalize or hash Event content."""
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (source, source_account, external_id)
    ):
        raise ValueError("Event source identity must contain nonempty strings")
    encoded = json.dumps(
        [source, source_account, external_id], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "event-source-v1:" + hashlib.sha256(encoded).hexdigest()


def validate_attachments(attachments: object) -> None:
    """Accept projected metadata only, including Graph's type annotation."""
    if not isinstance(attachments, (tuple, list)):
        raise ValueError("Attachments must be a metadata collection")
    allowed = {"id", "name", "contentType", "size", "isInline", "@odata.type"}
    for item in attachments:
        if not isinstance(item, dict) or not item or not item.keys() <= allowed:
            raise ValueError("Invalid attachment metadata")
        for name in ("id", "name", "contentType", "@odata.type"):
            if name in item and not isinstance(item[name], str):
                raise ValueError("Attachment text metadata must be strings")
        if "size" in item and (type(item["size"]) is not int or item["size"] < 0):
            raise ValueError("Attachment size must be a nonnegative integer")
        if "isInline" in item and type(item["isInline"]) is not bool:
            raise ValueError("Attachment inline metadata must be boolean")


@dataclass(frozen=True)
class Event:
    source: str
    source_account: str
    external_id: str
    occurred_at: datetime
    direction: str
    event_type: str
    parties: tuple[dict[str, Any], ...] = ()
    subject: str = ""
    body: str = ""
    attachments: tuple[dict[str, Any], ...] = ()
    client_id: str | None = None
    project_id: str | None = None
    job_id: str | None = None
    ai_summary: str | None = None
    ai_actions: tuple[str, ...] = ()
    needs_action: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def identity_key(self) -> str:
        return event_identity_key(self.source, self.source_account, self.external_id)

    def __post_init__(self) -> None:
        validate_attachments(self.attachments)
        if any(
            not value.strip()
            for value in (self.source, self.source_account, self.external_id, self.id)
        ):
            raise ValueError("Event identity fields must be nonempty")
        if self.event_type not in EVENT_TYPES or self.direction not in DIRECTIONS:
            raise ValueError("Unsupported Event type or direction")
        for value in (self.occurred_at, self.created_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Event timestamps must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        validate_attachments(self.attachments)
        payload = asdict(self)
        for name in ("occurred_at", "created_at"):
            payload[name] = getattr(self, name).astimezone(UTC).isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Event:
        values = dict(payload)
        validate_attachments(values.get("attachments"))
        for name in ("occurred_at", "created_at"):
            values[name] = datetime.fromisoformat(values[name])
        for name in ("parties", "attachments", "ai_actions"):
            values[name] = tuple(values[name])
        return cls(**values)
