"""Operations Inbox, usable without an email-memory database."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import streamlit as st

from edn.operations.storage import EventStore


def render_operations_inbox() -> None:
    st.header("Operations Inbox")
    setting = os.environ.get("EDN_OPERATIONS_DB", "")
    if not setting or not Path(setting).is_absolute() or not Path(setting).is_file():
        st.info("Configure EDN_OPERATIONS_DB with an existing Operations database.")
        return
    store = EventStore(Path(setting), read_only=True)
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
        result = store.list_events_with_diagnostics(
            needs_action=needs_action,
            source=filters.get("source"),
            client_id=filters.get("client_id"),
            project_id=filters.get("project_id"),
            job_id=filters.get("job_id"),
        )
        events = result.events
        st.caption("Newest activity first · up to 100 events · local read-only view")
        if result.malformed:
            st.warning(
                f"{result.malformed} malformed event(s) omitted from this page. "
                "The source records have not been changed."
            )
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
