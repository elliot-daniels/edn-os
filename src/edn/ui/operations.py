"""Operations Inbox, usable without an email-memory database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import streamlit as st

from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.storage import EventStore


def render_import_status(path: Path) -> None:
    """Bounded read-only history; persisted Events never imply intake completeness."""
    try:
        history = ImportOutcomeStore(path, read_only=True).latest(limit=20)
    except (sqlite3.Error, ValueError):
        st.warning("Import history is unavailable; completeness is unknown.")
        return
    if not history:
        st.caption("Import status: never run · no recorded import outcome.")
        return
    st.caption(
        "Latest recorded import per account within the 20 most recent attempts. "
        "Coverage applies only to the requested Inbox window."
    )
    seen: set[str] = set()
    for run in history:
        if run.source_account in seen:
            continue
        seen.add(run.source_account)
        state = (
            "In progress or interrupted · incomplete"
            if run.state == "in_progress"
            else run.state.capitalize()
        )
        st.text(f"Import status: {state} · {run.source_account}")
        st.caption(
            f"{run.window_start} to {run.window_end} · "
            f"recorded checkpoint: {run.inserted} inserted · "
            f"{run.duplicates} duplicates · "
            f"{run.failed} rejected records · {run.pages} completed pages"
        )
        if run.state == "in_progress":
            st.caption(
                "An interrupted run may have stored Events "
                "beyond these checkpoint counts."
            )
        if run.reason:
            reasons = {
                "malformed_records": "Malformed records were rejected.",
                "page_limit": "The page limit was reached before completion.",
                "import_error": "Import stopped with an error; coverage is incomplete.",
            }
            st.caption(reasons.get(run.reason, "Import completion is unconfirmed."))


def render_operations_inbox() -> None:
    st.header("Operations Inbox")
    setting = os.environ.get("EDN_OPERATIONS_DB", "")
    if not setting or not Path(setting).is_absolute() or not Path(setting).is_file():
        st.info("Configure EDN_OPERATIONS_DB with an existing Operations database.")
        return
    store = EventStore(Path(setting), read_only=True)
    render_import_status(Path(setting))
    try:
        needs_action = st.checkbox("Needs action only")
        filters: dict[str, str | None] = {}
        for field, label in (
            ("source", "Source"),
            ("client_id", "Client"),
            ("project_id", "Project"),
            ("job_id", "Job"),
        ):
            options = store.filter_values(field)
            if field != "source" and not options:
                continue
            choice = st.selectbox(label, ("All", *options))
            filters[field] = None if choice == "All" else choice
        events = store.list_events(
            needs_action=needs_action,
            source=filters.get("source"),
            client_id=filters.get("client_id"),
            project_id=filters.get("project_id"),
            job_id=filters.get("job_id"),
        )
        st.caption("Newest activity first · up to 100 events · local read-only view")
        if not events:
            st.info("No events match these filters.")
        for event in events:
            with st.container(border=True):
                st.text(event.subject or "(No subject)")
                st.caption(
                    f"{event.occurred_at.isoformat()} · {event.event_type} · "
                    f"{event.source} · {event.source_account} · {event.direction}"
                )
                if event.needs_action:
                    st.write("Needs action")
                for party in event.parties:
                    st.text(f"{party.get('role', '')}: {party.get('address', '')}")
                if event.ai_summary:
                    st.caption("AI summary (derived)")
                    st.text(event.ai_summary)
                for action in event.ai_actions:
                    st.text(f"Suggested action: {action}")
                with st.expander("Details and provenance"):
                    st.text(event.body)
                    for attachment in event.attachments:
                        st.text(str(attachment.get("name", "Attachment")))
                    for label, value in (
                        ("Client", event.client_id),
                        ("Project", event.project_id),
                        ("Job", event.job_id),
                    ):
                        if value:
                            st.text(f"{label}: {value}")
                    st.text(f"Source record: {event.external_id}")
                    st.text(f"Event: {event.id}")
    except (sqlite3.Error, ValueError):
        st.error("Operations database is unavailable or not initialized.")
