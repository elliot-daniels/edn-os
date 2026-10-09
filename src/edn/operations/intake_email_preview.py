"""Pure partial-draft scheduling preview; never creates a calendar appointment."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from typing import Any

from edn.operations.intake_email import _UNKNOWN
from edn.operations.intake_scheduling import (
    ADELAIDE,
    CalendarSnapshot,
    DurationEstimate,
    ScheduleProposal,
    SchedulingRequest,
    propose_schedule,
)


def preview_email_schedule(
    draft: dict[str, Any], calendar: CalendarSnapshot, *, now: datetime
) -> ScheduleProposal:
    """Only new jobs qualify; preserve explicit constraints and their uncertainty."""
    if draft.get("assessment_stale"):
        return ScheduleProposal(
            "needs_reassessment", reasons=("Older assessment requires audited review",)
        )
    assessment = draft["assessment"]
    if assessment["kind"] != "new_job":
        return ScheduleProposal(
            "not_applicable", reasons=("Correspondence is not a new job",)
        )
    values = {fact["field"]: fact["value"] for fact in assessment["facts"]}
    values.update({key: answer["value"] for key, answer in draft["answers"].items()})
    values = {
        key: value
        for key, value in values.items()
        if value.casefold().strip(" .") not in _UNKNOWN
    }
    requested_date = None
    requested_start = None
    if values.get("requested_date"):
        try:
            requested_date = date.fromisoformat(values["requested_date"])
            if values["requested_date"] != requested_date.isoformat():
                raise ValueError
        except ValueError:
            return ScheduleProposal(
                "needs_clarification", reasons=("Clarify requested date",)
            )
    if values.get("requested_time"):
        if requested_date is None:
            return ScheduleProposal(
                "needs_clarification", reasons=("Requested time needs a date",)
            )
        if not re.fullmatch(
            r"[0-2][0-9]:[0-5][0-9](?: Adelaide)?", values["requested_time"]
        ):
            return ScheduleProposal(
                "needs_clarification", reasons=("Clarify requested time and zone",)
            )
        try:
            local_time = time.fromisoformat(
                values["requested_time"].removesuffix(" Adelaide")
            )
            requested_start = datetime.combine(requested_date, local_time, ADELAIDE)
            alternate = requested_start.replace(fold=1)
            if (
                requested_start.utcoffset() != alternate.utcoffset()
                or requested_start.astimezone(UTC).astimezone(ADELAIDE)
                != requested_start
            ):
                raise ValueError
        except ValueError:
            return ScheduleProposal(
                "needs_clarification",
                reasons=("Requested local time is invalid or ambiguous",),
            )
    matched = re.fullmatch(
        r"([1-9][0-9]{0,3}) (minutes?|hours?)", values.get("duration", "")
    )
    minutes = 60
    reliable = False
    basis = "Unverified 60-minute planning estimate; ask operator for duration"
    if matched:
        minutes = int(matched[1]) * (60 if matched[2].startswith("hour") else 1)
        if minutes > 1440:
            return ScheduleProposal(
                "needs_clarification",
                reasons=("Duration exceeds one-day planning bound",),
            )
        reliable = True
        basis = "Duration explicitly reported in source or operator answer"
    return propose_schedule(
        SchedulingRequest(
            draft["source_key"],
            DurationEstimate(minutes, basis, reliable),
            bool(values.get("siteLocation")),
            requested_date,
            requested_start,
        ),
        calendar,
        now=now,
    )
