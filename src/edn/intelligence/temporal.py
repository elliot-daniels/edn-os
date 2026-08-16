"""Fail-closed PA-009 evidence freshness and temporal validity rules."""

from __future__ import annotations

from datetime import datetime, timedelta

from edn.intelligence.models import ContextEvidence, TemporalState

INBOX_RECENT_FOR = timedelta(days=7)
LOCAL_FILE_RECENT_FOR = timedelta(days=30)


def temporal_state(item: ContextEvidence, reference_time: datetime) -> TemporalState:
    """Derive temporal meaning only from trusted, already-admitted metadata."""

    if reference_time.tzinfo is None:
        raise ValueError("temporal reference time must be timezone-aware")
    if item.timestamp_kind == "calendar_event_end":
        start, end = item.temporal_start, item.temporal_end
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return TemporalState.UNKNOWN_UNDETERMINED
        if start.tzinfo is None or end.tzinfo is None:
            return TemporalState.UNKNOWN_UNDETERMINED
        if end < reference_time:
            return TemporalState.EXPIRED_PAST_EVENT
        if start > reference_time:
            return TemporalState.FUTURE
        return TemporalState.CURRENT_RECENT
    timestamp = item.source_timestamp
    if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
        return TemporalState.UNKNOWN_UNDETERMINED
    if timestamp > reference_time:
        return TemporalState.FUTURE
    if item.timestamp_kind in {"mail_received_at", "email_sent_at"}:
        threshold = INBOX_RECENT_FOR
    elif item.timestamp_kind == "file_modified_at":
        threshold = LOCAL_FILE_RECENT_FOR
    else:
        return TemporalState.UNKNOWN_UNDETERMINED
    return (
        TemporalState.CURRENT_RECENT
        if reference_time - timestamp <= threshold
        else TemporalState.STALE_HISTORICAL
    )


def projected_temporal_state_is_consistent(
    *,
    field_category: str,
    source_timestamp: datetime | None,
    state: TemporalState,
    reference_time: datetime,
) -> bool:
    """Independently reject manually projected temporal labels that contradict time."""

    if reference_time.tzinfo is None:
        return False
    if source_timestamp is None or source_timestamp.tzinfo is None:
        return state is TemporalState.UNKNOWN_UNDETERMINED
    if field_category == "calendar.metadata":
        if source_timestamp < reference_time:
            return state is TemporalState.EXPIRED_PAST_EVENT
        return state in {TemporalState.CURRENT_RECENT, TemporalState.FUTURE}
    if field_category == "inbox.metadata":
        expected = _timestamp_state(source_timestamp, reference_time, INBOX_RECENT_FOR)
        return state is expected
    if field_category == "local-files.metadata":
        expected = _timestamp_state(
            source_timestamp, reference_time, LOCAL_FILE_RECENT_FOR
        )
        return state is expected
    return state is TemporalState.UNKNOWN_UNDETERMINED


def _timestamp_state(
    timestamp: datetime, reference_time: datetime, recent_for: timedelta
) -> TemporalState:
    if timestamp > reference_time:
        return TemporalState.FUTURE
    if reference_time - timestamp <= recent_for:
        return TemporalState.CURRENT_RECENT
    return TemporalState.STALE_HISTORICAL
