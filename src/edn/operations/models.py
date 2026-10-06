"""Operations v1 Event contract; AI outputs never replace source content."""

from __future__ import annotations

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

    def __post_init__(self) -> None:
        validate_attachments(self.attachments)
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.source, self.source_account, self.external_id, self.id)
        ):
            raise ValueError("Event identity fields must be nonempty")
        for category in (self.event_type, self.direction):
            if not isinstance(category, str):
                raise ValueError("Event type and direction must be strings")
        if self.event_type not in EVENT_TYPES or self.direction not in DIRECTIONS:
            raise ValueError("Unsupported Event type or direction")
        for timestamp in (self.occurred_at, self.created_at):
            if (
                not isinstance(timestamp, datetime)
                or timestamp.tzinfo is None
                or timestamp.utcoffset() is None
            ):
                raise ValueError("Event timestamps must be timezone-aware")
        if not isinstance(self.subject, str) or not isinstance(self.body, str):
            raise ValueError("Event content must be text")
        for optional_text in (
            self.client_id,
            self.project_id,
            self.job_id,
            self.ai_summary,
        ):
            if optional_text is not None and not isinstance(optional_text, str):
                raise ValueError("Optional Event text must be strings")
        if type(self.needs_action) is not bool:
            raise ValueError("Event needs_action must be boolean")
        if not isinstance(self.raw_payload, dict):
            raise ValueError("Event raw payload must be an object")
        if not isinstance(self.parties, (tuple, list)) or any(
            not isinstance(party, dict)
            or any(
                name in party and not isinstance(party[name], str)
                for name in ("role", "address", "name")
            )
            for party in self.parties
        ):
            raise ValueError("Event parties must contain valid metadata objects")
        if not isinstance(self.ai_actions, (tuple, list)) or any(
            not isinstance(action, str) for action in self.ai_actions
        ):
            raise ValueError("Event actions must be text collections")

    def to_dict(self) -> dict[str, Any]:
        validate_attachments(self.attachments)
        payload = asdict(self)
        for name in ("occurred_at", "created_at"):
            payload[name] = getattr(self, name).astimezone(UTC).isoformat()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Event:
        if not isinstance(payload, dict):
            raise ValueError("Event payload must be an object")
        try:
            values = dict(payload)
            validate_attachments(values.get("attachments"))
            for name in ("occurred_at", "created_at"):
                values[name] = datetime.fromisoformat(values[name])
            for name in ("parties", "attachments", "ai_actions"):
                if not isinstance(values[name], (tuple, list)):
                    raise ValueError("Event metadata must be collections")
                values[name] = tuple(values[name])
            return cls(**values)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Malformed Event payload") from error
