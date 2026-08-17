"""Conservative Microsoft 365 calendar records and bounded time windows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Self
from zoneinfo import ZoneInfo

from edn.core import Classification, SecurityDomain


class CalendarWindow(StrEnum):
    TODAY = "today"
    NEXT_7_DAYS = "next-7-days"
    THIS_WEEK = "this-week"
    LAST_7_DAYS = "last-7-days"

    def bounds(self, now: datetime, timezone_name: str) -> tuple[datetime, datetime]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        local = now.astimezone(ZoneInfo(timezone_name))
        day = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if self is CalendarWindow.TODAY:
            return day, day + timedelta(days=1)
        if self is CalendarWindow.NEXT_7_DAYS:
            return local, local + timedelta(days=7)
        if self is CalendarWindow.LAST_7_DAYS:
            return local - timedelta(days=7), local
        monday = day - timedelta(days=day.weekday())
        return monday, monday + timedelta(days=7)


class CalendarScopeMode(StrEnum):
    DEDICATED_EDN = "dedicated-edn"
    CATEGORY_REQUIRED = "category-required"


@dataclass(frozen=True, slots=True)
class CalendarConfig:
    tenant_id: str
    account_id: str
    calendar_id: str
    calendar_name: str
    timezone_name: str
    security_domain: SecurityDomain
    classification: Classification
    scope_mode: CalendarScopeMode
    required_category: str | None = None
    include_body: bool = False

    def __post_init__(self) -> None:
        for value in (self.tenant_id, self.account_id, self.calendar_id):
            if not value.strip() or any(character in value for character in "\r\n"):
                raise ValueError("calendar identity values must be nonblank")
        ZoneInfo(self.timezone_name)
        if self.include_body:
            raise ValueError("IC-009 does not authorize calendar body retrieval")
        if self.scope_mode is CalendarScopeMode.CATEGORY_REQUIRED:
            if self.required_category is None or not self.required_category.strip():
                raise ValueError("category-required mode needs an exact category")
        elif self.required_category is not None:
            raise ValueError("dedicated-calendar mode does not accept a category")


@dataclass(frozen=True, slots=True)
class CalendarAttendee:
    name: str
    address: str
    response: str


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_id: str
    calendar_id: str
    subject: str
    start: datetime
    end: datetime
    timezone_name: str
    organizer: str
    attendees: tuple[CalendarAttendee, ...]
    location: str | None
    is_all_day: bool
    recurrence: str | None
    web_url: str | None
    last_modified_at: datetime
    categories: tuple[str, ...]
    security_domain: SecurityDomain
    classification: Classification

    def __post_init__(self) -> None:
        if not self.event_id or not self.calendar_id or not self.subject.strip():
            raise ValueError("event identity and subject must be nonblank")
        for value in (self.start, self.end, self.last_modified_at):
            if value.tzinfo is None:
                raise ValueError("calendar timestamps must be timezone-aware")
        if self.end < self.start:
            raise ValueError("event end must not precede start")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "calendar_id": self.calendar_id,
            "subject": self.subject,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "timezone_name": self.timezone_name,
            "organizer": self.organizer,
            "attendees": [
                {"name": item.name, "address": item.address, "response": item.response}
                for item in self.attendees
            ],
            "location": self.location,
            "is_all_day": self.is_all_day,
            "recurrence": self.recurrence,
            "web_url": self.web_url,
            "last_modified_at": self.last_modified_at.isoformat(),
            "categories": list(self.categories),
            "security_domain": self.security_domain.to_dict(),
            "classification": self.classification.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        attendees = value.get("attendees")
        if not isinstance(attendees, list):
            raise ValueError("attendees must be a list")
        return cls(
            str(value["event_id"]),
            str(value["calendar_id"]),
            str(value["subject"]),
            datetime.fromisoformat(str(value["start"])),
            datetime.fromisoformat(str(value["end"])),
            str(value["timezone_name"]),
            str(value["organizer"]),
            tuple(
                CalendarAttendee(
                    str(item["name"]), str(item["address"]), str(item["response"])
                )
                for item in attendees
            ),
            None if value.get("location") is None else str(value["location"]),
            value.get("is_all_day") is True,
            None if value.get("recurrence") is None else str(value["recurrence"]),
            None if value.get("web_url") is None else str(value["web_url"]),
            datetime.fromisoformat(str(value["last_modified_at"])),
            tuple(str(item) for item in value.get("categories", [])),
            SecurityDomain.from_dict(_mapping(value["security_domain"])),
            Classification.from_dict(_mapping(value["classification"])),
        )


@dataclass(frozen=True, slots=True)
class CalendarRetrievalResult:
    """Counts all bounded Graph objects but retains admitted EDN events only."""

    pre_filter_count: int
    events: tuple[CalendarEvent, ...]
    rejection_reasons: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.pre_filter_count < 0:
            raise ValueError("pre_filter_count must not be negative")
        if self.admitted_count > self.pre_filter_count:
            raise ValueError("admitted_count must not exceed pre_filter_count")

    @property
    def admitted_count(self) -> int:
        return len(self.events)

    @property
    def rejected_count(self) -> int:
        return self.pre_filter_count - self.admitted_count

    def counts_dict(self) -> dict[str, int]:
        return {
            "pre_filter_count": self.pre_filter_count,
            "admitted_count": self.admitted_count,
            "rejected_count": self.rejected_count,
        }

    def rejection_reasons_dict(self) -> dict[str, int]:
        """Return content-free reasons for bounded non-admission."""
        return dict(self.rejection_reasons)


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("serialized model must be an object")
    return value
