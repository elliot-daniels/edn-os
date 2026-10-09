"""Independent scheduling acceptance cases; no network or live calendar."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from edn.connectors.microsoft_calendar.models import CalendarEvent
from edn.core import Classification, SecurityDomain
from edn.operations.intake_scheduling import (
    ADELAIDE,
    PROVISIONAL,
    CalendarSnapshot,
    DurationEstimate,
    SchedulingRequest,
    propose_schedule,
)

NOW = datetime(2026, 10, 12, 9, tzinfo=ADELAIDE)


def snapshot(now=NOW, events=(), complete=True):
    return CalendarSnapshot(
        now, now + timedelta(days=7), now, events, complete, "synthetic-calendar"
    )


def request(**kwargs):
    return SchedulingRequest(
        "job-1", DurationEstimate(60, "confirmed email duration", True), True, **kwargs
    )


def event(start, end):
    return CalendarEvent(
        "busy",
        "synthetic-calendar",
        "Existing commitment",
        start,
        end,
        "Australia/Adelaide",
        "operator@example.test",
        (),
        None,
        False,
        None,
        None,
        NOW,
        (),
        SecurityDomain("EDN", "EDN synthetic"),
        Classification("edn", "internal", "Synthetic", 1),
    )


def test_earliest_slot_reserves_buffers_and_never_claims_confirmation():
    result = propose_schedule(request(), snapshot(), now=NOW)
    assert result.status == "provisional_eligible"
    assert result.start == datetime(2026, 10, 12, 10, 30, tzinfo=ADELAIDE)
    assert result.end == datetime(2026, 10, 12, 11, 30, tzinfo=ADELAIDE)
    assert result.occupied_start.hour == 10
    assert result.occupied_end.hour == 12
    assert result.title == PROVISIONAL


def test_existing_commitment_blocks_service_and_travel_buffer():
    busy = event(
        datetime(2026, 10, 12, 11, 45, tzinfo=ADELAIDE),
        datetime(2026, 10, 12, 12, tzinfo=ADELAIDE),
    )
    result = propose_schedule(request(), snapshot(events=(busy,)), now=NOW)
    assert result.occupied_start == busy.end
    assert result.start.hour == 12 and result.start.minute == 30


def test_explicit_requested_time_conflict_is_not_silently_rescheduled():
    start = datetime(2026, 10, 12, 11, tzinfo=ADELAIDE)
    busy = event(start, start + timedelta(hours=1))
    result = propose_schedule(
        request(requested_start=start), snapshot(events=(busy,)), now=NOW
    )
    assert result.status == "conflict" and result.start is None


def test_explicit_date_fully_busy_never_moves_to_another_day():
    day = date(2026, 10, 12)
    busy = event(
        datetime(2026, 10, 12, 0, tzinfo=ADELAIDE),
        datetime(2026, 10, 13, 0, tzinfo=ADELAIDE),
    )
    result = propose_schedule(
        request(requested_date=day), snapshot(events=(busy,)), now=NOW
    )
    assert result.status == "conflict"


def test_uncertain_duration_or_site_is_proposal_only():
    draft = replace(
        request(),
        duration=DurationEstimate(60, "unverified scope estimate", False),
        site_ready=False,
    )
    result = propose_schedule(draft, snapshot(), now=NOW)
    assert result.status == "proposal_only" and len(result.reasons) == 2


@pytest.mark.parametrize("days_ago,complete", [(0, False), (1, True), (-1, True)])
def test_incomplete_stale_or_future_calendar_never_books(days_ago, complete):
    coverage = replace(
        snapshot(), checked_at=NOW - timedelta(days=days_ago), complete=complete
    )
    assert propose_schedule(request(), coverage, now=NOW).status == "calendar_unknown"


def test_weekend_is_skipped_and_past_time_is_never_booked():
    saturday = datetime(2026, 10, 10, 12, tzinfo=ADELAIDE)
    result = propose_schedule(request(), snapshot(saturday), now=saturday)
    assert result.start.weekday() == 0 and result.start.day == 12
    assert (
        propose_schedule(
            request(requested_start=NOW - timedelta(days=1)), snapshot(), now=NOW
        ).status
        == "conflict"
    )


@pytest.mark.parametrize(
    "day,offset",
    [(date(2026, 10, 2), 9.5), (date(2026, 10, 5), 10.5), (date(2027, 4, 5), 9.5)],
)
def test_adelaide_dst_and_utc_busy_intervals(day, offset):
    now = datetime(day.year, day.month, day.day, 9, tzinfo=ADELAIDE)
    busy_start = now.replace(hour=10).astimezone(UTC)
    busy = event(busy_start, busy_start + timedelta(hours=1))
    result = propose_schedule(request(), snapshot(now, events=(busy,)), now=now)
    assert result.start.utcoffset().total_seconds() / 3600 == offset
    assert result.start.hour == 11 and result.start.minute == 30


def test_job_does_not_split_and_replay_reservation_key_is_stable():
    long = replace(request(), duration=DurationEstimate(301, "confirmed", True))
    assert propose_schedule(long, snapshot(), now=NOW).status == "no_fit"
    first = propose_schedule(request(), snapshot(), now=NOW)
    revised = propose_schedule(
        request(requested_date=date(2026, 10, 13)), snapshot(), now=NOW
    )
    assert first.reservation_key == revised.reservation_key


def test_naive_time_and_contradictory_explicit_constraints_refused():
    with pytest.raises(ValueError):
        propose_schedule(request(), snapshot(), now=datetime(2026, 10, 12, 9))
    with pytest.raises(ValueError):
        request(requested_date=date(2026, 10, 13), requested_start=NOW)


def test_customer_night_work_is_preserved_as_exception_proposal():
    night = NOW.replace(hour=22)
    result = propose_schedule(request(requested_start=night), snapshot(), now=NOW)
    assert result.start == night
    assert result.end == night + timedelta(hours=1)
    assert result.status == "proposal_only"
    assert "outside default" in result.reasons[0]
    busy = event(night, night + timedelta(minutes=10))
    assert (
        propose_schedule(
            request(requested_start=night), snapshot(events=(busy,)), now=NOW
        ).status
        == "conflict"
    )


def test_default_search_never_escapes_five_working_days():
    coverage = replace(snapshot(), end=NOW + timedelta(days=21))
    busy = event(NOW.replace(hour=0), NOW.replace(hour=0) + timedelta(days=5))
    coverage = replace(coverage, events=(busy,))
    assert propose_schedule(request(), coverage, now=NOW).status == "no_slot"


def test_explicit_weekend_date_is_not_replaced_by_monday():
    result = propose_schedule(
        request(requested_date=date(2026, 10, 17)), snapshot(), now=NOW
    )
    assert result.start.date() == date(2026, 10, 17)
    assert result.status == "proposal_only"


def test_spring_dst_buffer_cannot_miss_real_overlap():
    now = datetime(2026, 10, 3, 9, tzinfo=ADELAIDE)
    start = datetime(2026, 10, 4, 3, 15, tzinfo=ADELAIDE)
    busy = event(start, start + timedelta(minutes=30))
    result = propose_schedule(
        request(requested_start=start), snapshot(now, (busy,)), now=now
    )
    assert result.status == "conflict"


def test_fall_dst_explicit_fold_preserved_and_duration_is_elapsed_time():
    now = datetime(2027, 4, 3, 9, tzinfo=ADELAIDE)
    start = datetime(2027, 4, 4, 2, 45, tzinfo=ADELAIDE, fold=1)
    result = propose_schedule(request(requested_start=start), snapshot(now), now=now)
    assert result.start.astimezone(UTC) == start.astimezone(UTC)
    assert result.start.fold == 1
    assert result.end.astimezone(UTC) - result.start.astimezone(UTC) == timedelta(
        minutes=60
    )
    assert result.start.astimezone(UTC) - result.occupied_start.astimezone(
        UTC
    ) == timedelta(minutes=30)


def test_nonexistent_explicit_wall_time_is_refused():
    with pytest.raises(ValueError, match="does not exist"):
        request(requested_start=datetime(2026, 10, 4, 2, 45, tzinfo=ADELAIDE))


def test_future_starting_snapshot_does_not_move_next_five_day_horizon():
    future = replace(
        snapshot(), start=NOW + timedelta(days=7), end=NOW + timedelta(days=14)
    )
    result = propose_schedule(request(), future, now=NOW)
    assert result.status == "calendar_unknown" and result.start is None


@pytest.mark.parametrize("explicit", [False, True])
def test_truncated_calendar_is_unknown_not_conflict_or_no_slot(explicit):
    truncated = replace(snapshot(), end=NOW.replace(hour=15))
    asked = (
        request(requested_start=NOW + timedelta(days=1, hours=2))
        if explicit
        else request()
    )
    result = propose_schedule(asked, truncated, now=NOW)
    assert result.status == "calendar_unknown"
