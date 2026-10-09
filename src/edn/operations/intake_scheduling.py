"""Pure provisional planning over complete authorised calendar snapshots.

No transport, external action, customer confirmation or live reservation exists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from edn.connectors.microsoft_calendar.models import CalendarEvent

ADELAIDE = ZoneInfo("Australia/Adelaide")
PROVISIONAL = "Provisional — Awaiting Confirmation"


def _aware(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("Scheduling timestamps must be timezone-aware")
    if value.astimezone(UTC).astimezone(value.tzinfo).replace(
        tzinfo=None
    ) != value.replace(tzinfo=None):
        raise ValueError("Scheduling local timestamp does not exist")


@dataclass(frozen=True, slots=True)
class DurationEstimate:
    minutes: int
    basis: str
    reliable: bool

    def __post_init__(self) -> None:
        if type(self.minutes) is not int or not 1 <= self.minutes <= 1440:
            raise ValueError("Duration must be bounded positive minutes")
        if not self.basis.strip() or type(self.reliable) is not bool:
            raise ValueError("Duration requires explicit evidence and uncertainty")


@dataclass(frozen=True, slots=True)
class SchedulingRequest:
    job_id: str
    duration: DurationEstimate
    site_ready: bool
    requested_date: date | None = None
    requested_start: datetime | None = None
    before_minutes: int = 30
    after_minutes: int = 30

    def __post_init__(self) -> None:
        if (
            not isinstance(self.job_id, str)
            or not self.job_id.strip()
            or type(self.site_ready) is not bool
        ):
            raise ValueError("Job identity and explicit site readiness are required")
        if self.requested_date is not None and type(self.requested_date) is not date:
            raise ValueError("Requested day must be a date")
        for value in (self.before_minutes, self.after_minutes):
            if type(value) is not int or not 0 <= value <= 180:
                raise ValueError("Travel/preparation buffers must be bounded")
        if self.requested_start is not None:
            _aware(self.requested_start)
            if self.requested_date is not None and (
                self.requested_start.astimezone(ADELAIDE).date() != self.requested_date
            ):
                raise ValueError("Explicit date and time disagree")


@dataclass(frozen=True, slots=True)
class CalendarSnapshot:
    start: datetime
    end: datetime
    checked_at: datetime
    events: tuple[CalendarEvent, ...]
    complete: bool
    scope_ref: str

    def __post_init__(self) -> None:
        _aware(self.start)
        _aware(self.end)
        _aware(self.checked_at)
        if (
            not timedelta(0)
            < self.end.astimezone(UTC) - self.start.astimezone(UTC)
            <= timedelta(days=31)
        ):
            raise ValueError("Calendar coverage must be positive and bounded")
        if not self.scope_ref.strip() or type(self.complete) is not bool:
            raise ValueError("Calendar scope and completeness must be explicit")
        if len(self.events) > 5000:
            raise ValueError("Calendar snapshot exceeds event bound")
        if type(self.events) is not tuple or any(
            not isinstance(event, CalendarEvent) for event in self.events
        ):
            raise ValueError("Calendar snapshot requires immutable typed events")
        for event in self.events:
            _aware(event.start)
            _aware(event.end)


@dataclass(frozen=True, slots=True)
class ScheduleProposal:
    status: str
    start: datetime | None = None
    end: datetime | None = None
    occupied_start: datetime | None = None
    occupied_end: datetime | None = None
    reservation_key: str | None = None
    title: str = PROVISIONAL
    reasons: tuple[str, ...] = ()


def propose_schedule(
    request: SchedulingRequest, snapshot: CalendarSnapshot, *, now: datetime
) -> ScheduleProposal:
    """Return earliest unsplit slot; never relax an explicit requested date/time.

    Buffers occupy the same 10-15 work window. All admitted calendar commitments
    block conservatively, including all-day events. Incomplete coverage fails
    closed, and estimates can produce proposals but never reservation eligibility.
    """
    _aware(now)
    age = now.astimezone(UTC) - snapshot.checked_at.astimezone(UTC)
    if not snapshot.complete or not timedelta(0) <= age <= timedelta(minutes=5):
        return ScheduleProposal("calendar_unknown", reasons=("Incomplete calendar",))
    before = timedelta(minutes=request.before_minutes)
    after = timedelta(minutes=request.after_minutes)
    duration = timedelta(minutes=request.duration.minutes)
    if request.requested_start is None and before + duration + after > timedelta(
        hours=5
    ):
        return ScheduleProposal("no_fit", reasons=("Unsplit job exceeds work window",))
    local_now = now.astimezone(ADELAIDE)
    now_utc = now.astimezone(UTC)
    first = local_now.date()
    explicit_day = request.requested_date
    if request.requested_start is not None:
        explicit_day = request.requested_start.astimezone(ADELAIDE).date()
    days = (
        [explicit_day]
        if explicit_day is not None
        else [
            first + timedelta(days=offset)
            for offset in range(32)
            if (first + timedelta(days=offset)).weekday() < 5
            and datetime.combine(first + timedelta(days=offset), time(15), ADELAIDE)
            > local_now
        ][:5]
    )
    # Availability needs coverage of the real horizon, not a horizon shifted to
    # whatever future range the caller happened to retrieve.
    if explicit_day is None and days:
        required_start = max(
            now_utc, datetime.combine(days[0], time(10), ADELAIDE).astimezone(UTC)
        )
        required_end = datetime.combine(days[-1], time(15), ADELAIDE).astimezone(UTC)
        if (
            snapshot.start.astimezone(UTC) > required_start
            or snapshot.end.astimezone(UTC) < required_end
        ):
            return ScheduleProposal(
                "calendar_unknown", reasons=("Five-workday horizon is not covered",)
            )
    for day in days:
        window_start = datetime.combine(day, time(10), ADELAIDE).astimezone(UTC)
        window_end = datetime.combine(day, time(15), ADELAIDE).astimezone(UTC)
        if day.weekday() >= 5 and explicit_day is None:
            continue
        outside_default = day.weekday() >= 5
        if request.requested_start is not None:
            candidate = request.requested_start.astimezone(UTC) - before
            requested_finish = candidate + before + duration + after
            outside_default = (
                outside_default
                or candidate < window_start
                or requested_finish > window_end
            )
            window_start, window_end = candidate, requested_finish
        else:
            candidate = max(window_start, now_utc)
            # Minute boundary avoids pretending a mid-minute arrival is exact.
            if candidate.second or candidate.microsecond:
                candidate = candidate.replace(second=0, microsecond=0) + timedelta(
                    minutes=1
                )
        if window_end <= now_utc or candidate < now_utc:
            continue
        if candidate < snapshot.start.astimezone(
            UTC
        ) or window_end > snapshot.end.astimezone(UTC):
            return ScheduleProposal(
                "calendar_unknown", reasons=("Requested occupancy is not covered",)
            )
        while candidate + before + duration + after <= window_end:
            finish = candidate + before + duration + after
            if candidate < window_start or candidate < now_utc:
                break
            if candidate < snapshot.start or finish > snapshot.end:
                break
            conflicts = [
                event
                for event in snapshot.events
                if candidate.astimezone(UTC) < event.end.astimezone(UTC)
                and finish.astimezone(UTC) > event.start.astimezone(UTC)
            ]
            if not conflicts:
                reasons = tuple(
                    reason
                    for condition, reason in (
                        (
                            outside_default,
                            "Customer requirement outside default work window",
                        ),
                        (not request.site_ready, "Site/access requires clarification"),
                        (
                            not request.duration.reliable,
                            "Duration is an uncertain estimate",
                        ),
                    )
                    if condition
                )
                return ScheduleProposal(
                    "proposal_only" if reasons else "provisional_eligible",
                    (candidate + before).astimezone(ADELAIDE),
                    (candidate + before + duration).astimezone(ADELAIDE),
                    candidate.astimezone(ADELAIDE),
                    finish.astimezone(ADELAIDE),
                    hashlib.sha256(
                        ("edn-provisional-v1:" + request.job_id).encode()
                    ).hexdigest(),
                    reasons=reasons,
                )
            if request.requested_start is not None:
                break
            candidate = max(event.end.astimezone(UTC) for event in conflicts)
    reason = (
        "Requested date/time unavailable"
        if explicit_day
        else "No suitable covered slot"
    )
    return ScheduleProposal(
        "conflict" if explicit_day else "no_slot", reasons=(reason,)
    )
