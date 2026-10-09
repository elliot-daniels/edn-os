"""Opt-in synthetic email pilot inside the existing local Work Intake app."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from edn.operations.intake_email_drafts import EmailDraftStore
from edn.operations.intake_email_preview import preview_email_schedule
from edn.operations.intake_scheduling import ADELAIDE, CalendarSnapshot
from edn.operations.models import Event


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


def render_email_pilot(root: Path) -> None:
    st.subheader("Email intake · synthetic pilot")
    st.caption(
        "Fictional email and empty-calendar fixtures. "
        "No mailbox read or appointment created."
    )
    path = root / "email-drafts.db"
    try:
        if st.button("Load synthetic email examples", key="email-pilot-load"):
            store = EmailDraftStore(path)
            store.initialise()
            for event in synthetic_examples():
                store.ingest(event)
            st.success(
                "Synthetic examples saved. Loading again preserves existing answers."
            )
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
    with st.expander(f"{original['subject']} · {assessment['kind']}", expanded=True):
        st.caption(
            f"Revision {record['revision']} · unapproved draft · no SharePoint delivery"
        )
        st.write("Classification: " + assessment["kind"])
        for fact in assessment["facts"]:
            st.write(f"{fact['field']}: {fact['value']} (reported in email)")
        for field, answer in record["answers"].items():
            st.write(f"{field}: {answer['value']} (operator confirmed)")
        proposal = preview_email_schedule(record, calendar, now=now)
        if proposal.status == "not_applicable":
            st.info("No schedule proposed for this correspondence.")
        elif proposal.start is not None:
            st.write("Provisional — Awaiting Confirmation")
            st.write(proposal.start.strftime("%a %d %b %Y, %H:%M") + " Adelaide")
            st.caption(
                "Planning preview only · no reservation or customer appointment exists"
            )
            if proposal.status == "proposal_only":
                st.warning("Requirements need clarification before booking.")
        else:
            st.warning("No suitable proposal: " + "; ".join(proposal.reasons))
        questions = record["outstanding_questions"]
        for question in questions:
            st.write(f"{question['category']}: {question['question']}")
        if assessment["kind"] == "new_job":
            fields = tuple(
                dict.fromkeys(
                    [
                        *(q["field"] for q in questions),
                        *(f["field"] for f in assessment["facts"]),
                        *record["answers"],
                        "requested_date",
                        "requested_time",
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
                    EmailDraftStore(path).answer(
                        key, record["revision"], field, value, actor="local-operator"
                    )
                    st.rerun()
                except (ValueError, sqlite3.Error, OSError):
                    st.error("Answer was not confirmed. Refresh and check your value.")
        with st.expander("Original evidence and provenance"):
            st.caption("Source identity: " + key)
            st.text(original["body"])
            st.json(record["history"])
