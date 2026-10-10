"""Opt-in synthetic email pilot inside the existing local Work Intake app."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from edn.operations.intake import IntakeStore
from edn.operations.intake_email_drafts import EmailDraftStore
from edn.operations.intake_email_preview import preview_email_schedule
from edn.operations.intake_reservation_calendar import include_local_reservations
from edn.operations.intake_reservations import SyntheticReservationStore
from edn.operations.intake_scheduling import (
    ADELAIDE,
    CalendarSnapshot,
    ScheduleProposal,
)
from edn.operations.models import Event
from edn.ui.intake_hold_review import render_hold_review


def synthetic_examples() -> tuple[Event, ...]:
    """Fictional examples only; never representations of unread owner mail."""
    examples = (
        (
            "New work request",
            "Customer: Synthetic Depot Co\nSite: Synthetic depot\n"
            "Scope: Repair network switch\nJob reference: SYNTH-JOB-01\n"
            "Duration: 90 minutes",
        ),
        (
            "New job request",
            "Customer: Example Facilities Co\nSite: Example warehouse\n"
            "Scope: Replace switch\nJob reference: SYNTH-JOB-02",
        ),
        ("Remittance advice", "Synthetic payment notice. No work requested."),
        ("For your information", "Synthetic newsletter. No work requested."),
        ("Following up", "Any update on our previous request?"),
        ("Hello", "Please get in touch about an unclear matter."),
    )
    return tuple(
        Event(
            source="synthetic_email_pilot",
            source_account="fixture@example.test",
            external_id=f"fixture-{index}",
            occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
            direction="inbound",
            event_type="email",
            subject=subject,
            body=body,
        )
        for index, (subject, body) in enumerate(examples, 1)
    )


def synthetic_forwarded_example() -> Event:
    """Complete fictional forward; embedded addresses are not verified contacts."""
    return Event(
        source="synthetic_email_pilot",
        source_account="fixture@example.test",
        external_id="fixture-explicit-forward",
        occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
        direction="inbound",
        event_type="email",
        subject="Fwd: New work request",
        body=(
            "Please prepare the forwarded work request.\n\n"
            "---------- Forwarded message ----------\n"
            "From: Unverified sender <sender@example.test>\n"
            "Subject: New work request\n\n"
            "Customer: Synthetic Forward Co\nContact: Synthetic Contact\n"
            "Email: contact@example.test\nPhone: 0400000000\n"
            "Site: Synthetic forward depot\nScope: Replace failed switch\n"
            "Duration: 90 minutes\nJob reference: SYNTH-FORWARD-01"
        ),
    )


def render_email_pilot(root: Path) -> None:
    st.subheader("Email intake · synthetic pilot")
    st.caption(
        "Fictional email and empty-calendar fixtures. "
        "No mailbox read or appointment created."
    )
    path = root / "email-drafts.db"
    render_hold_review(root)
    try:
        if st.button("Load synthetic email examples", key="email-pilot-load"):
            store = EmailDraftStore(path)
            store.initialise()
            for event in synthetic_examples():
                store.ingest(event)
            st.success(
                "Synthetic examples saved. Loading again preserves existing answers."
            )
        if st.button(
            "Load synthetic forwarded request", key="email-pilot-load-forward"
        ):
            store = EmailDraftStore(path)
            store.initialise()
            store.ingest(synthetic_forwarded_example())
            st.success("Fictional forward saved; embedded sender remains unverified.")
        if not path.is_file():
            st.info("Load examples to try job preparation. No real email is accessed.")
            return
        reader = EmailDraftStore(path, read_only=True)
        records, malformed = reader.list_drafts(limit=100)
        if malformed:
            st.warning(
                f"{malformed} malformed email drafts isolated; "
                "other records remain available."
            )
        now = datetime.now(ADELAIDE)
        calendar = CalendarSnapshot(
            now, now + timedelta(days=10), now, (), True, "synthetic-empty-calendar"
        )
        if (root / "reservations.db").exists() or (
            root / "reservations.db"
        ).is_symlink():
            try:
                calendar = include_local_reservations(
                    calendar,
                    SyntheticReservationStore(root / "reservations.db", read_only=True),
                    IntakeStore(root / "requests.db", read_only=True),
                )
                st.caption(
                    f"{len(calendar.events)} verified synthetic local holds "
                    "included in planning; none is a customer confirmation."
                )
                for hold in calendar.events:
                    st.text(
                        f"Synthetic hold {hold.event_id}: travel/preparation occupancy "
                        f"{hold.start.isoformat()} → {hold.end.isoformat()}"
                    )
            except (ValueError, sqlite3.Error, OSError):
                calendar = replace(calendar, complete=False)
                st.error(
                    "Local reservations could not be verified. Scheduling is "
                    "blocked until review; no interval is treated as free."
                )
        for record in records:
            _render_draft(path, record, calendar, now)
    except (ValueError, sqlite3.Error, OSError):
        st.error(
            "Email pilot storage is unavailable. "
            "No scheduling or delivery is confirmed."
        )


def _render_draft(
    path: Path, record: dict[str, Any], calendar: CalendarSnapshot, now: datetime
) -> None:
    original = record["original"]
    assessment = record["assessment"]
    key = record["source_key"]
    # Source text must not become Markdown images/links or fetch remote resources.
    label = "Email " + key.rsplit(":", 1)[-1][:8] + " · " + assessment["kind"]
    with st.expander(label, expanded=True):
        result = st.session_state.pop(key + "-action-result", None)
        if result is not None:
            st.success(
                f"Local job action verified: revision {result[0]}, "
                f"state {result[1]}. Review the Intake queue."
            )
            st.warning(
                "No calendar reservation was changed. Review scheduling "
                "separately before relying on an appointment."
            )
        st.text(original["subject"])
        st.caption(
            f"Revision {record['revision']} · unapproved draft · no SharePoint delivery"
        )
        st.write("Classification: " + assessment["kind"])
        if st.checkbox("Show source details and change history", key=key + "-evidence"):
            st.write("Retained source · reported content, not verified sender identity")
            st.text(
                f"Source: {original['source']}\n"
                f"Account: {original['source_account']}\n"
                f"Message: {original['external_id']}\n"
                f"Source event time: {original['occurred_at']}\n"
                f"Source hash: {record['source_hash']}"
            )
            st.write("Extraction evidence · exact quotes from original email")
            for fact in assessment["facts"]:
                st.text(f"{fact['field']}: {fact['quote']}")
            history = record["history"]
            st.caption(
                f"Most recent {min(20, len(history))} of {len(history)} changes. "
                "Full history remains stored."
            )
            for entry in history[-20:]:
                st.text(
                    f"Revision {entry['revision']} · {entry.get('action', 'recorded')}"
                    f" · {entry['actor']} · {entry['at']}"
                )
                if entry.get("action") == "answered":
                    previous = entry.get("previous")
                    before = (
                        previous.get("value", "Not previously answered")
                        if isinstance(previous, dict)
                        else "Not previously answered"
                    )
                    st.text(f"{entry.get('field')}: {before} → {entry.get('value')}")
        if record.get("assessment_stale"):
            st.warning(
                "Older assessment preserved. "
                "Scheduling and answers are blocked until review."
            )
            if st.button("Reassess synthetic example", key=key + "-reassess"):
                try:
                    EmailDraftStore(path).reassess_synthetic(
                        key, record["revision"], actor="local-operator"
                    )
                    st.rerun()
                except (ValueError, sqlite3.Error, OSError):
                    st.error(
                        "Reassessment was not confirmed. "
                        "Original evidence remains retained."
                    )
            st.text(original["body"])
            return
        for fact in assessment["facts"]:
            st.text(f"{fact['field']}: {fact['value']} (reported in email)")
        for field, answer in record["answers"].items():
            st.text(f"{field}: {answer['value']} (operator confirmed)")
        try:
            requests_path = path.parent / "requests.db"
            current_job = (
                EmailDraftStore(path, read_only=True).linked_job(
                    key, IntakeStore(requests_path, read_only=True)
                )
                if requests_path.is_file()
                else None
            )
            proposal = preview_email_schedule(
                record, calendar, now=now, current_job=current_job
            )
            if current_job is not None and any(
                hold.calendar_id == "synthetic-local-reservations"
                and hold.event_id == current_job.request_id
                for hold in calendar.events
            ):
                proposal = ScheduleProposal(
                    "already_reserved",
                    reasons=("Current job already has a synthetic provisional hold",),
                )
        except (ValueError, sqlite3.Error, OSError):
            proposal = ScheduleProposal(
                "job_unknown",
                reasons=("Current job could not be verified; review before planning",),
            )
        if proposal.status == "not_applicable":
            st.info("No schedule proposed for this correspondence.")
        elif proposal.status == "already_reserved":
            st.info(
                "This job already has a verified synthetic provisional hold. "
                "Review its occupancy above; no second proposal or confirmed "
                "customer appointment is created."
            )
        elif proposal.start is not None:
            st.write("Provisional — Awaiting Confirmation")
            assert proposal.end is not None
            assert (
                proposal.occupied_start is not None
                and proposal.occupied_end is not None
            )
            st.write(
                "Service: "
                + proposal.start.strftime("%a %d %b %Y %H:%M %z")
                + " → "
                + proposal.end.strftime("%a %d %b %Y %H:%M %z")
                + " Adelaide"
            )
            st.write(
                "Travel/preparation occupancy: "
                + proposal.occupied_start.strftime("%a %d %b %Y %H:%M %z")
                + " → "
                + proposal.occupied_end.strftime("%a %d %b %Y %H:%M %z")
                + " Adelaide"
            )
            minutes = int(
                (
                    proposal.end.astimezone(UTC) - proposal.start.astimezone(UTC)
                ).total_seconds()
                / 60
            )
            if "Duration is an uncertain estimate" in proposal.reasons:
                st.warning(
                    f"Unverified {minutes}-minute planning estimate; confirm duration."
                )
            else:
                st.caption(
                    f"{minutes}-minute duration explicitly reported "
                    "in email or operator answer."
                )
            for reason in proposal.reasons:
                st.write("Qualification: " + reason)
            st.caption(
                "Planning preview only · no reservation or customer appointment exists"
            )
            if proposal.status == "proposal_only":
                st.warning("Requirements need clarification before booking.")
            if (
                proposal.status == "provisional_eligible"
                and current_job is not None
                and st.button(
                    "Reserve synthetic provisional hold", key=key + "-reserve"
                )
            ):
                try:
                    ledger = SyntheticReservationStore(path.parent / "reservations.db")
                    ledger.initialise()
                    # Use the external synthetic snapshot; the ledger adds all
                    # retained local occupancy under its own mutation lock.
                    base_calendar = replace(
                        calendar,
                        events=tuple(
                            event
                            for event in calendar.events
                            if event.calendar_id != "synthetic-local-reservations"
                        ),
                    )
                    EmailDraftStore(path).reserve_job(
                        key,
                        record["revision"],
                        IntakeStore(path.parent / "requests.db"),
                        ledger,
                        base_calendar,
                        expected_reservation_revision=0,
                        now=now,
                    )
                    st.rerun()
                except (ValueError, sqlite3.Error, OSError):
                    st.error(
                        "Reservation was not confirmed. Refresh and review "
                        "current job and availability; no customer appointment "
                        "exists."
                    )
        else:
            st.warning("No suitable proposal: " + "; ".join(proposal.reasons))
        questions = record["outstanding_questions"]
        for question in questions:
            st.write(f"{question['category']}: {question['question']}")
        if (
            assessment["kind"] in {"job_update", "cancellation"}
            and (path.parent / "requests.db").is_file()
        ):
            cancellation = assessment["kind"] == "cancellation"
            st.caption(
                "Synthetic local job action only. Calendar reservations are separate; "
                "no customer message or Microsoft write will occur."
            )
            confirmed = not cancellation or st.checkbox(
                "Confirm cancellation of the matching synthetic job",
                key=key + "-confirm-cancel",
            )
            if st.button(
                "Apply synthetic cancellation"
                if cancellation
                else "Apply synthetic update",
                key=key + "-apply-action",
                disabled=not confirmed,
            ):
                try:
                    store = EmailDraftStore(path)
                    requests = IntakeStore(path.parent / "requests.db")
                    action = store.cancel_job if cancellation else store.update_job
                    job = action(key, record["revision"], requests)
                    st.session_state[key + "-action-result"] = (job.revision, job.state)
                    st.rerun()
                except (ValueError, sqlite3.Error, OSError):
                    st.error(
                        "Job action was not confirmed. Check source details and "
                        "canonical matching; no scheduling or delivery is confirmed."
                    )
        if assessment["kind"] == "new_job":
            editor_key = key + "-editor-revision"
            if editor_key not in st.session_state:
                st.session_state[editor_key] = record["revision"]
            expected_revision = st.session_state[editor_key]
            if expected_revision != record["revision"]:
                st.warning(
                    "This draft changed in another session. Refresh before saving."
                )
                if st.button("Refresh email editor", key=key + "-refresh"):
                    st.session_state[editor_key] = record["revision"]
                    st.session_state.pop(key + "-field", None)
                    st.session_state.pop(key + "-answer", None)
                    st.rerun()
                return
            fields = tuple(
                dict.fromkeys(
                    [
                        *(q["field"] for q in questions),
                        *(f["field"] for f in assessment["facts"]),
                        *record["answers"],
                        "requested_date",
                        "requested_time",
                        "email",
                        "phone",
                    ]
                )
            )
            field = st.selectbox(
                "Answer or correct a field", fields, key=key + "-field"
            )
            value = st.text_input(
                "Answer (dates YYYY-MM-DD; time HH:MM Adelaide; "
                "duration e.g. 90 minutes)",
                key=key + "-answer",
            )
            if st.button("Save answer", key=key + "-save"):
                try:
                    updated = EmailDraftStore(path).answer(
                        key,
                        expected_revision,
                        field,
                        value,
                        actor="local-operator",
                        requests=(
                            IntakeStore(path.parent / "requests.db")
                            if (path.parent / "requests.db").is_file()
                            else None
                        ),
                    )
                    st.session_state[editor_key] = updated["revision"]
                    st.rerun()
                except (ValueError, sqlite3.Error, OSError):
                    st.error("Answer was not confirmed. Refresh and check your value.")
            values = {fact["field"]: fact["value"] for fact in assessment["facts"]}
            values.update(
                {name: answer["value"] for name, answer in record["answers"].items()}
            )
            for name in ("email", "phone"):
                if not values.get(name):
                    st.write(
                        f"before_attending: Supply contact {name} for job preparation."
                    )
            if (path.parent / "requests.db").is_file() and st.button(
                "Prepare or refresh job", key=key + "-materialise"
            ):
                try:
                    job = EmailDraftStore(path).materialise(
                        key, expected_revision, IntakeStore(path.parent / "requests.db")
                    )
                    st.success(
                        "Canonical job prepared. Review it in Intake queue; "
                        "approval and SharePoint delivery are separate."
                    )
                    if job.source_pending:
                        st.warning(
                            "Updated source requires review before approval or export."
                        )
                except (ValueError, sqlite3.Error, OSError):
                    st.error(
                        "Job preparation was not confirmed. Check required fields and "
                        "evidence; no approval or delivery is confirmed."
                    )
        with st.expander("Original evidence and provenance"):
            st.caption("Source identity: " + key)
            st.text(original["body"])
            st.json(record["history"])
