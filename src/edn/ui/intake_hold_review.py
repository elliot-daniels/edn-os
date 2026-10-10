"""Opt-in synthetic hold review; no job edit, external event or confirmation."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import streamlit as st

from edn.operations.intake import IntakeStore, _digest
from edn.operations.intake_reservations import SyntheticReservationStore


def render_hold_review(root: Path) -> None:
    path = root / "reservations.db"
    if not path.exists() and not path.is_symlink():
        return
    with st.expander("Review synthetic provisional holds"):
        try:
            rows = SyntheticReservationStore(path, read_only=True).list_reservations()
            if not rows:
                st.info("No retained synthetic holds.")
                return
            selected = st.selectbox(
                "Synthetic hold to review",
                tuple(row["job_id"] for row in rows),
                key="hold-review-selection",
            )
            item = next(row for row in rows if row["job_id"] == selected)
            last = item["history"][-1]
            st.text(
                f"Hold revision {item['revision']} · {item['state']}\n"
                f"Original occupancy: {last['plan']['occupied_start']} "
                f"→ {last['plan']['occupied_end']}"
            )
            st.caption(
                "Synthetic internal history only; no customer appointment or "
                "Microsoft event is changed."
            )
            if item["state"] == "cancelled":
                st.info(
                    "Synthetic hold released; original interval and history retained."
                )
                return
            requests = IntakeStore(root / "requests.db", read_only=True)
            with requests._connect() as connection:
                job = requests._get(connection, selected)
                if requests._canonical(connection, selected) != selected:
                    raise ValueError("Aliased hold requires canonical review")
            digest = _digest(job.fields, job.attachments)
            st.text(
                f"Current job revision {job.revision} · {job.state}\n"
                f"Site: {job.fields['siteLocation']}\n"
                f"Scope: {job.fields['jobDescription']}"
            )
            stale = (
                job.state in {"cancelled", "rejected"}
                or job.source_pending
                or job.revision != last["job_revision"]
                or digest != last["job_hash"]
            )
            if not stale:
                st.info("Current matching hold; no stale-release action is available.")
                return
            st.warning(
                "This hold no longer matches the current job. Review and release "
                "the stale occupancy before relying on scheduling."
            )
            key = f"hold-{selected}-{item['revision']}-{job.revision}-{digest}"
            confirmed = st.checkbox(
                "Confirm release of this stale synthetic hold", key=key
            )
            if st.button(
                "Release stale synthetic hold",
                key=key + "-release",
                disabled=not confirmed,
            ):
                SyntheticReservationStore(path).release_stale_for_job(
                    IntakeStore(root / "requests.db"),
                    selected,
                    job_revision=job.revision,
                    job_hash=digest,
                    expected_revision=item["revision"],
                    actor="local-operator",
                    now=datetime.now(UTC),
                )
                st.rerun()
        except (ValueError, sqlite3.Error, OSError):
            st.error(
                "Hold review or release was not confirmed. Refresh and inspect "
                "the current job and retained history; no interval is assumed free."
            )
