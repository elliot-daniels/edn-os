"""Durable synthetic internal reservations; no Outlook transport or confirmation.

The caller supplies the canonical job version/hash. This ledger does not attest
that a job exists or is approved; canonical-job integration is a separate gate.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from edn.connectors.microsoft_calendar.models import CalendarEvent
from edn.core import Classification, SecurityDomain
from edn.operations.intake import IntakeError, IntakeStore, _digest
from edn.operations.intake_scheduling import (
    PROVISIONAL,
    CalendarSnapshot,
    SchedulingRequest,
    _aware,
    propose_schedule,
)

_DDL = """CREATE TABLE reservations (
job_id TEXT PRIMARY KEY,
record TEXT NOT NULL
)"""


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 200
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise IntakeError("Reservation actor or reason is invalid")
    return value.strip()


def _identity(job_id: str, job_revision: int, job_hash: str) -> None:
    try:
        valid = str(UUID(job_id)) == job_id
    except (ValueError, TypeError, AttributeError):
        valid = False
    if (
        not valid
        or type(job_revision) is not int
        or job_revision < 1
        or not isinstance(job_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", job_hash) is None
    ):
        raise IntakeError("Reservation requires an exact canonical job version/hash")


class _ReservationBackend(IntakeStore):
    @staticmethod
    def _validate(connection: sqlite3.Connection) -> None:
        if connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall() != [("reservations", _DDL)] or connection.execute(
            "PRAGMA user_version"
        ).fetchone() != (1,):
            raise IntakeError("Unsupported reservation schema")

    def initialise(self) -> None:
        self._write()
        with self._connect(initialise=True) as connection:
            if connection.execute("PRAGMA user_version").fetchone() == (1,):
                return
            connection.execute(_DDL)
            connection.execute("PRAGMA user_version=1")


class SyntheticReservationStore:
    """Serialise planning and persistence under the existing protected-store lock."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self._backend = _ReservationBackend(path, read_only=read_only)

    def initialise(self) -> None:
        self._backend.initialise()

    @staticmethod
    def _rows(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        result = {}
        try:
            for job_id, payload in connection.execute(
                "SELECT job_id,record FROM reservations ORDER BY job_id"
            ):
                item = json.loads(payload)
                if set(item) != {"job_id", "revision", "state", "history"}:
                    raise ValueError
                if item["job_id"] != job_id or type(item["revision"]) is not int:
                    raise ValueError
                history = item["history"]
                if not isinstance(history, list) or len(history) != item["revision"]:
                    raise ValueError
                for index, entry in enumerate(history, 1):
                    if (
                        set(entry)
                        != {
                            "revision",
                            "action",
                            "actor",
                            "at",
                            "reason",
                            "job_revision",
                            "job_hash",
                            "request_hash",
                            "calendar_scope",
                            "checked_at",
                            "plan",
                        }
                        or entry["revision"] != index
                    ):
                        raise ValueError
                    _identity(job_id, entry["job_revision"], entry["job_hash"])
                    _text(entry["actor"])
                    _text(entry["reason"])
                    if entry["action"] not in {"reserved", "rescheduled", "cancelled"}:
                        raise ValueError
                    if index == 1 and entry["action"] != "reserved":
                        raise ValueError
                    for name in ("at", "checked_at"):
                        timestamp = datetime.fromisoformat(entry[name])
                        _aware(timestamp)
                        if timestamp.utcoffset() != UTC.utcoffset(timestamp):
                            raise ValueError
                    if re.fullmatch(
                        r"[0-9a-f]{64}", entry["request_hash"]
                    ) is None or not entry["calendar_scope"].startswith("synthetic-"):
                        raise ValueError
                    plan = entry["plan"]
                    if (
                        set(plan)
                        != {
                            "start",
                            "end",
                            "occupied_start",
                            "occupied_end",
                            "title",
                            "reservation_key",
                        }
                        or plan["title"] != PROVISIONAL
                    ):
                        raise ValueError
                    expected_key = hashlib.sha256(
                        ("edn-provisional-v1:" + job_id).encode()
                    ).hexdigest()
                    if plan["reservation_key"] != expected_key:
                        raise ValueError
                    times = [
                        datetime.fromisoformat(plan[n])
                        for n in ("occupied_start", "start", "end", "occupied_end")
                    ]
                    for timestamp in times:
                        _aware(timestamp)
                    a, b, c, d = [t.astimezone(UTC) for t in times]
                    if not a <= b < c <= d:
                        raise ValueError
                state = (
                    "cancelled"
                    if history[-1]["action"] == "cancelled"
                    else "provisional"
                )
                if item["state"] != state:
                    raise ValueError
                result[job_id] = item
            if len(result) > 1000:
                raise ValueError
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
            RecursionError,
        ):
            # Corrupt busy data must never be ignored and permit double booking.
            raise IntakeError("Reservation ledger integrity is invalid") from None
        return result

    def list_reservations(self) -> tuple[dict[str, Any], ...]:
        with self._backend._connect() as connection:
            return tuple(self._rows(connection).values())

    def reserve(
        self,
        request: SchedulingRequest,
        snapshot: CalendarSnapshot,
        *,
        job_revision: int,
        job_hash: str,
        expected_revision: int,
        now: datetime,
        actor: str,
    ) -> dict[str, Any]:
        """Plan from fresh synthetic availability plus every active local hold.

        expected_revision=0 creates; replay returns the same receipt. Reschedule
        requires the displayed ledger revision. No uncertain proposal is reserved.
        """
        self._backend._write()
        _identity(request.job_id, job_revision, job_hash)
        _aware(now)
        actor = _text(actor)
        if type(expected_revision) is not int or expected_revision < 0:
            raise IntakeError("Invalid reservation revision")
        if not snapshot.scope_ref.startswith("synthetic-"):
            raise IntakeError("Only synthetic calendar snapshots are permitted")
        request_values = asdict(request)
        for name in ("requested_date", "requested_start"):
            value = getattr(request, name)
            request_values[name] = value.isoformat() if value is not None else None
        request_hash = hashlib.sha256(_json(request_values).encode()).hexdigest()
        with self._backend._connect() as connection:
            rows = self._rows(connection)
            previous = rows.get(request.job_id)
            if previous:
                last = previous["history"][-1]
                if previous["state"] == "provisional" and (
                    last["job_revision"],
                    last["job_hash"],
                    last["request_hash"],
                ) == (job_revision, job_hash, request_hash):
                    return previous
                if previous["revision"] != expected_revision:
                    raise IntakeError(
                        "Reservation changed; refresh before rescheduling"
                    )
                if job_revision < last["job_revision"] or (
                    job_revision == last["job_revision"]
                    and job_hash != last["job_hash"]
                ):
                    raise IntakeError("Canonical job version/hash conflicts")
            elif expected_revision != 0 or len(rows) >= 1000:
                raise IntakeError("Reservation revision or ledger capacity is invalid")
            busy = []
            for job_id, item in rows.items():
                if job_id == request.job_id or item["state"] == "cancelled":
                    continue
                plan = item["history"][-1]["plan"]
                busy.append(
                    CalendarEvent(
                        job_id,
                        "synthetic-local-reservations",
                        PROVISIONAL,
                        datetime.fromisoformat(plan["occupied_start"]),
                        datetime.fromisoformat(plan["occupied_end"]),
                        "Australia/Adelaide",
                        "synthetic@example.test",
                        (),
                        None,
                        False,
                        None,
                        None,
                        now,
                        (),
                        SecurityDomain("EDN", "EDN synthetic"),
                        Classification("edn", "internal", "Synthetic", 1),
                    )
                )
            proposal = propose_schedule(
                request, replace(snapshot, events=(*snapshot.events, *busy)), now=now
            )
            if proposal.status != "provisional_eligible":
                raise IntakeError(
                    "Fresh conflict-free reliable scheduling evidence is required"
                )
            plan = {
                name: getattr(proposal, name).isoformat()
                for name in ("start", "end", "occupied_start", "occupied_end")
            }
            plan.update(title=PROVISIONAL, reservation_key=proposal.reservation_key)
            history = previous["history"][:] if previous else []
            revision = len(history) + 1
            history.append(
                {
                    "revision": revision,
                    "action": "rescheduled" if previous else "reserved",
                    "actor": actor,
                    "at": now.astimezone(UTC).isoformat(),
                    "reason": "Synthetic internal hold; awaiting confirmation",
                    "job_revision": job_revision,
                    "job_hash": job_hash,
                    "request_hash": request_hash,
                    "calendar_scope": snapshot.scope_ref,
                    "checked_at": snapshot.checked_at.astimezone(UTC).isoformat(),
                    "plan": plan,
                }
            )
            item = {
                "job_id": request.job_id,
                "revision": revision,
                "state": "provisional",
                "history": history,
            }
            connection.execute(
                "INSERT OR REPLACE INTO reservations VALUES (?,?)",
                (request.job_id, _json(item)),
            )
            return item

    def reserve_for_job(
        self,
        request: SchedulingRequest,
        snapshot: CalendarSnapshot,
        requests: IntakeStore,
        *,
        job_revision: int,
        job_hash: str,
        expected_revision: int,
        now: datetime,
        actor: str,
    ) -> dict[str, Any]:
        """Publish a synthetic hold while the verified canonical job is locked.

        Job-then-ledger ordering matches read-only projection. Explicit caller
        duration/readiness remain scheduling evidence, not inferred authority.
        Later job changes need reconciliation; this does not couple mutations.
        """
        _identity(request.job_id, job_revision, job_hash)
        with requests._connect() as connection:
            job = requests._get(connection, request.job_id)
            if (
                requests._canonical(connection, job.request_id) != job.request_id
                or job.state not in {"draft", "approved"}
                or job.source_pending
                or job.revision != job_revision
                or _digest(job.fields, job.attachments) != job_hash
            ):
                raise IntakeError("Canonical job changed or requires review")
            if job.fields[
                "preferredDate"
            ] and request.requested_date != date.fromisoformat(
                job.fields["preferredDate"]
            ):
                raise IntakeError("Preserve the canonical requested date")
            return self.reserve(
                request,
                snapshot,
                job_revision=job_revision,
                job_hash=job_hash,
                expected_revision=expected_revision,
                now=now,
                actor=actor,
            )

    def release_stale_for_job(
        self,
        requests: IntakeStore,
        job_id: str,
        *,
        job_revision: int,
        job_hash: str,
        expected_revision: int,
        actor: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Release only a verified stale synthetic hold; retain its full audit.

        Keep the current canonical job locked through ledger cancellation. An
        unchanged active binding is not releasable through this recovery API.
        Malformed/aliased jobs and concurrent ledger revisions require review.
        """
        _identity(job_id, job_revision, job_hash)
        with requests._connect() as connection:
            job = requests._get(connection, job_id)
            if (
                requests._canonical(connection, job_id) != job_id
                or job.revision != job_revision
                or _digest(job.fields, job.attachments) != job_hash
            ):
                raise IntakeError("Canonical job changed; refresh before release")
            with self._backend._connect() as ledger:
                item = self._rows(ledger).get(job_id)
                if item is None or item["revision"] != expected_revision:
                    raise IntakeError("Reservation changed; refresh before release")
                last = item["history"][-1]
                if item["state"] != "cancelled" and (
                    job.state in {"draft", "approved"}
                    and not job.source_pending
                    and last["job_revision"] == job_revision
                    and last["job_hash"] == job_hash
                ):
                    raise IntakeError("Current matching hold is not stale")
            # cancel rechecks the displayed ledger revision under its mutation
            # lock. The job lock remains held across the read/publish boundary.
            return self.cancel(
                job_id,
                expected_revision,
                actor=actor,
                reason=(
                    f"Synthetic stale hold release: job revision {job_revision} "
                    f"hash {job_hash}; state {job.state}; pending {job.source_pending}"
                ),
                now=now,
            )

    def cancel(
        self,
        job_id: str,
        expected_revision: int,
        *,
        actor: str,
        reason: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Retain the original intervals and every prior revision in the audit."""
        self._backend._write()
        actor, reason = _text(actor), _text(reason)
        _aware(now)
        if type(expected_revision) is not int or expected_revision < 1:
            raise IntakeError("Invalid reservation revision")
        with self._backend._connect() as connection:
            item = self._rows(connection).get(job_id)
            if item is None or item["revision"] != expected_revision:
                raise IntakeError("Reservation changed; refresh before cancellation")
            if item["state"] == "cancelled":
                return item
            entry = dict(item["history"][-1])
            entry.update(
                revision=item["revision"] + 1,
                action="cancelled",
                actor=actor,
                reason=reason,
                at=now.astimezone(UTC).isoformat(),
            )
            item["history"].append(entry)
            item.update(revision=entry["revision"], state="cancelled")
            connection.execute(
                "UPDATE reservations SET record=? WHERE job_id=?", (_json(item), job_id)
            )
            return item
