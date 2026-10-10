"""Protected incomplete email drafts; complete-request approval gates stay intact.

The tiny internal backend reuses IntakeStore's Linux snapshot/locking protection.
It owns a separate schema, so incomplete facts cannot masquerade as an approved
manual request. Public workflow composition does not inherit request operations.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edn.operations.intake import (
    INPUT_FIELDS,
    IntakeError,
    IntakeRequest,
    IntakeStore,
    _audit_row,
    _digest,
    _record_identity,
    validate_fields,
)
from edn.operations.intake_email import (
    _UNKNOWN,
    ASSESSMENT_VERSION,
    EmailAssessment,
    EmailKind,
    assess_email,
)
from edn.operations.intake_email_reconciliation import match_email_job
from edn.operations.models import Event

_DDL = """CREATE TABLE email_drafts (
source_key TEXT PRIMARY KEY,
source_hash TEXT NOT NULL,
original TEXT NOT NULL,
revision INTEGER NOT NULL CHECK(revision > 0),
assessment TEXT NOT NULL,
answers TEXT NOT NULL,
history TEXT NOT NULL
)"""
_ANSWER_FIELDS = frozenset(
    {
        "company",
        "contactName",
        "email",
        "phone",
        "siteLocation",
        "jobDescription",
        "reference",
        "equipment",
        "requested_date",
        "requested_time",
        "duration",
        "access_requirements",
    }
)


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _text(value: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise IntakeError("Draft answer or actor text is invalid")
    return value.strip()


def _payload(assessment: EmailAssessment) -> dict[str, object]:
    return {
        "version": ASSESSMENT_VERSION,
        "kind": assessment.kind.value,
        "facts": [
            {
                "field": f.field,
                "value": f.value,
                "quote": f.quote,
                "source_key": f.source_key,
                "basis": f.basis,
            }
            for f in assessment.facts
        ],
        "questions": [
            {"field": q.field, "category": q.category, "question": q.question}
            for q in assessment.questions
        ],
        "reasons": list(assessment.reasons),
    }


def _event(original: dict[str, Any]) -> Event:
    # Stored JSON types are checked by Event's existing domain contract.
    values = dict(original)
    timestamp = values["occurred_at"]
    if not isinstance(timestamp, str):
        raise ValueError
    values["occurred_at"] = datetime.fromisoformat(timestamp)
    return Event(**values)


class _EmailSnapshotStore(IntakeStore):
    """Storage-only adapter; shares snapshot publication, never manual validation."""

    @staticmethod
    def _validate(connection: sqlite3.Connection) -> None:
        tables = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if (
            tables != [("email_drafts", _DDL)]
            or connection.execute("PRAGMA user_version").fetchone()[0] != 1
        ):
            raise IntakeError("Unsupported email draft schema")

    def initialise(self) -> None:
        self._write()
        with self._connect(initialise=True) as connection:
            if connection.execute("PRAGMA user_version").fetchone()[0] == 1:
                return
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_DDL)
            connection.execute("PRAGMA user_version=1")
            connection.commit()


class EmailDraftStore:
    """Durable partial records, immutable source receipts and audited continuation.

    There is no approval, export, calendar or source-mutation method. Forwarded
    identity headers never grant linkage. Cross-source reconciliation remains a
    separate requirement before unattended scheduling is possible.
    """

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self._backend = _EmailSnapshotStore(path, read_only=read_only)

    def initialise(self) -> None:
        self._backend.initialise()

    def ingest(
        self, event: Event, *, actor: str = "synthetic-email-intake"
    ) -> dict[str, object]:
        self._backend._write()
        actor = _text(actor, 100)
        assessment = assess_email(event)
        original = event.to_dict()
        # Local UUID/import timestamp and AI overlay are not source identity.
        source = {
            key: original[key]
            for key in (
                "source",
                "source_account",
                "external_id",
                "occurred_at",
                "direction",
                "event_type",
                "parties",
                "subject",
                "body",
                "attachments",
                "raw_payload",
            )
        }
        encoded = _json(source)
        if len(encoded.encode("utf-8")) > 1_048_576:
            raise IntakeError("Email source exceeds draft receipt bound")
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        payload = _payload(assessment)
        with self._backend._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT source_hash FROM email_drafts WHERE source_key=?",
                (event.identity_key,),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise IntakeError("Source replay conflicts with immutable receipt")
                return self._get(connection, event.identity_key)
            if (
                connection.execute("SELECT count(*) FROM email_drafts").fetchone()[0]
                >= 1000
            ):
                raise IntakeError("Synthetic pilot draft bound reached")
            history = [
                {
                    "revision": 1,
                    "actor": actor,
                    "at": datetime.now(UTC).isoformat(),
                    "action": "ingested",
                    "source_hash": digest,
                }
            ]
            connection.execute(
                "INSERT INTO email_drafts VALUES (?,?,?,1,?,'{}',?)",
                (event.identity_key, digest, encoded, _json(payload), _json(history)),
            )
            connection.commit()
            return self._get(connection, event.identity_key)

    @staticmethod
    def _get(connection: sqlite3.Connection, source_key: str) -> dict[str, object]:
        row = connection.execute(
            "SELECT source_hash,original,revision,assessment,answers,history "
            "FROM email_drafts WHERE source_key=?",
            (source_key,),
        ).fetchone()
        if row is None:
            raise IntakeError("Email draft is unavailable")
        try:
            original = json.loads(row[1])
            assessment = json.loads(row[3])
            answers = json.loads(row[4])
            history = json.loads(row[5])
            if (
                not isinstance(original, dict)
                or not isinstance(assessment, dict)
                or not isinstance(answers, dict)
                or not isinstance(history, list)
                or type(row[2]) is not int
                or row[2] < 1
                or len(history) != row[2]
                or hashlib.sha256(row[1].encode("utf-8")).hexdigest() != row[0]
            ):
                raise ValueError
            for revision, entry in enumerate(history, 1):
                if (
                    not isinstance(entry, dict)
                    or entry.get("revision") != revision
                    or entry.get("source_hash") != row[0]
                ):
                    raise ValueError
                _text(entry["actor"], 100)
                timestamp = datetime.fromisoformat(entry["at"])
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    raise ValueError
            expected = assess_email(_event(original))
            version = assessment.get("version", 1)
            if (
                type(version) is not int
                or not 1 <= version <= ASSESSMENT_VERSION
                or expected.source_key != source_key
            ):
                raise ValueError
            stale = version != ASSESSMENT_VERSION
            if not stale and assessment != _payload(expected):
                raise ValueError
            if stale:
                EmailKind(assessment["kind"])
                for name in ("facts", "questions", "reasons"):
                    if not isinstance(assessment[name], list):
                        raise ValueError
                for fact in assessment["facts"]:
                    if (
                        fact["field"] not in _ANSWER_FIELDS
                        or fact["basis"] != "email_reported"
                        or fact["source_key"] != source_key
                        or fact["quote"] not in original["body"]
                    ):
                        raise ValueError
                    value = fact["value"]
                    # Legacy source facts use the extraction contract, not the
                    # stricter operator-input contract. They remain unapproved
                    # source evidence and are rendered as inert text.
                    if (
                        not isinstance(value, str)
                        or not value.strip()
                        or len(value) > 2000
                        or any(ord(c) < 32 for c in value)
                    ):
                        raise ValueError
                for question in assessment["questions"]:
                    if question["field"] not in _ANSWER_FIELDS or question[
                        "category"
                    ] not in {
                        "before_scheduling",
                        "before_attending",
                        "before_invoicing",
                        "optional",
                    }:
                        raise ValueError
                    _text(question["question"], 2000)
            for field, answer in answers.items():
                if field not in _ANSWER_FIELDS or not isinstance(answer, dict):
                    raise ValueError
                _text(answer["value"], 2000)
                _text(answer["actor"], 100)
                if answer.get("basis") != "operator_confirmed":
                    raise ValueError
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            raise IntakeError("Stored email draft is malformed") from None
        return {
            "source_key": source_key,
            "source_hash": row[0],
            "original": original,
            "revision": row[2],
            "assessment": assessment,
            "assessment_stale": stale,
            "answers": answers,
            "history": history,
            "state": "unapproved_email_draft",
            "outstanding_questions": [
                question
                for question in assessment.get("questions", [])
                if question["field"] not in answers
                or answers[question["field"]]["value"].casefold().strip(" .")
                in _UNKNOWN
            ],
        }

    def get(self, source_key: str) -> dict[str, object]:
        with self._backend._connect() as connection:
            return self._get(connection, source_key)

    def materialise(
        self, source_key: str, expected_revision: int, requests: IntakeStore
    ) -> IntakeRequest:
        """Promote a complete synthetic draft with source-bound replay receipts.

        Lock ordering is draft then request. No request operation takes a draft
        lock. A restart after request publication safely replays the same source;
        there is no second cross-store write or receipt to reconcile.
        """
        self._backend._write()
        if type(expected_revision) is not int or expected_revision < 1:
            raise IntakeError("Invalid email draft revision")
        with self._backend._connect() as connection:
            draft = self._get(connection, source_key)
            if draft["revision"] != expected_revision or draft["assessment_stale"]:
                raise IntakeError("Email draft changed; refresh before job creation")
            original, assessment, answers = (
                draft["original"],
                draft["assessment"],
                draft["answers"],
            )
            assert isinstance(original, dict) and isinstance(assessment, dict)
            assert isinstance(answers, dict)
            if (
                not original["source"].startswith("synthetic_")
                or assessment["kind"] != EmailKind.NEW_JOB.value
            ):
                raise IntakeError("Only synthetic new-job drafts can create jobs")
            if original["attachments"]:
                raise IntakeError(
                    "Protect and associate source attachments before job creation"
                )
            values = {f["field"]: f["value"] for f in assessment["facts"]}
            values.update({name: answer["value"] for name, answer in answers.items()})
            defaults = {"serviceRequired": "Other / not sure", "urgency": "Routine"}
            fields = {name: values.get(name, "") for name in INPUT_FIELDS}
            fields.update(defaults)
            fields["preferredDate"] = values.get("requested_date", "")
            # Surface the existing actionable field diagnostic before the source
            # contract's deliberately generic corrupt-record error boundary.
            fields = validate_fields(fields)
            identity = {
                "source_system": "email",
                "event_source": original["source"],
                "source_account": original["source_account"],
                "native_item_id": original["external_id"],
            }
            payload = {
                **fields,
                "source": "EDN OS Email",
                "contractVersion": "1.0",
                "submittedAt": datetime.fromisoformat(original["occurred_at"])
                .astimezone(UTC)
                .isoformat(),
                "email_receipt": {
                    "identity": identity,
                    "event_source_key": draft["source_key"],
                    "source_hash": draft["source_hash"],
                    "draft_revision": draft["revision"],
                    "assessment_version": assessment["version"],
                    "facts": assessment["facts"],
                    "answers": answers,
                    "defaults": defaults,
                },
            }
            return requests._import_source(payload, identity)

    def linked_job(
        self, source_key: str, requests: IntakeStore
    ) -> IntakeRequest | None:
        """Read the protected source binding without materialising or editing it.

        Follow the existing draft-first lock order. Linked aliases require
        explicit canonical review rather than assuming their original proposal
        describes the currently selected work.
        """
        with self._backend._connect() as source_connection:
            draft = self._get(source_connection, source_key)
            original = draft["original"]
            assert isinstance(original, dict)
            if not original["source"].startswith("synthetic_"):
                raise IntakeError("Only synthetic job associations are permitted")
            identity = _record_identity(
                {
                    "source_system": "email",
                    "event_source": original["source"],
                    "source_account": original["source_account"],
                    "native_item_id": original["external_id"],
                },
                original["external_id"],
            )
            bound_key = hashlib.sha256(_json(identity).encode()).hexdigest()
            with requests._connect() as connection:
                requests._source_schema(connection)
                row = connection.execute(
                    "SELECT request_id FROM intake_sources WHERE source_key=?",
                    (bound_key,),
                ).fetchone()
                if row is None:
                    return None
                job = requests._get(connection, row[0])
                if requests._canonical(connection, job.request_id) != job.request_id:
                    raise IntakeError("Linked work requires current canonical review")
                return job

    def cancel_job(
        self, source_key: str, expected_revision: int, requests: IntakeStore
    ) -> IntakeRequest:
        """Reconcile and audit one synthetic cancellation under the request lock.

        Draft then request is the existing lock order. No calendar transport or
        reservation coupling is implied. Source identity/hash bind replay to the
        immutable retained email, not to an embedded sender or forwarded header.
        """
        self._backend._write()
        requests._write()
        if type(expected_revision) is not int or expected_revision < 1:
            raise IntakeError("Invalid cancellation draft revision")
        with self._backend._connect() as source_connection:
            draft = self._get(source_connection, source_key)
            if draft["revision"] != expected_revision or draft["assessment_stale"]:
                raise IntakeError("Email draft changed; refresh before cancellation")
            original = draft["original"]
            assert isinstance(original, dict)
            event = _event(original)
            assessment = assess_email(event)
            if (
                not event.source.startswith("synthetic_")
                or assessment.kind != EmailKind.CANCELLATION
            ):
                raise IntakeError("Only synthetic cancellation drafts can cancel jobs")
            reason = (
                f"Synthetic email cancellation: {source_key} {draft['source_hash']}"
            )
            with requests._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                requests._source_schema(connection)
                receipts = connection.execute(
                    "SELECT request_id,revision,content_hash FROM intake_approvals "
                    "WHERE decision='cancelled' AND reason=?",
                    (reason,),
                ).fetchall()
                if receipts:
                    if len(receipts) != 1:
                        raise IntakeError("Cancellation replay audit is inconsistent")
                    identifier, revision, digest = receipts[0]
                    replay = requests._get(connection, identifier)
                    if (
                        replay.state != "cancelled"
                        or replay.revision != revision
                        or _digest(replay.fields, replay.attachments) != digest
                        or requests._canonical(connection, identifier) != identifier
                    ):
                        raise IntakeError("Cancellation replay audit is inconsistent")
                    return replay
                rows = connection.execute(
                    "SELECT request_id FROM intake_requests LIMIT 1001"
                ).fetchall()
                if len(rows) > 1000:
                    raise IntakeError("Cancellation snapshot exceeds its bound")
                jobs = []
                for (identifier,) in rows:
                    job = requests._get(connection, identifier)
                    if requests._canonical(connection, identifier) == identifier:
                        jobs.append(job)
                proposal = match_email_job(event, assessment, jobs, complete=True)
                if proposal.status != "matched_proposal":
                    raise IntakeError(
                        "Cancellation requires review: " + proposal.status
                    )
                assert proposal.target_id is not None
                job = requests._get(connection, proposal.target_id)
                if (
                    job.revision != proposal.target_revision
                    or _digest(job.fields, job.attachments) != proposal.target_hash
                ):
                    raise IntakeError("Cancellation target changed")
                requests._record_revision(
                    connection, job, job.fields, "cancelled", reason
                )
                connection.execute(
                    "UPDATE intake_requests SET state='cancelled' WHERE request_id=?",
                    (job.request_id,),
                )
                return requests._get(connection, job.request_id)

    def update_job(
        self, source_key: str, expected_revision: int, requests: IntakeStore
    ) -> IntakeRequest:
        """Apply a bounded synthetic canonical update with durable source replay.

        Scheduling-only facts are not silently omitted. Matching and mutation
        use one request snapshot/lock, following the existing draft-first order.
        """
        self._backend._write()
        requests._write()
        if type(expected_revision) is not int or expected_revision < 1:
            raise IntakeError("Invalid update draft revision")
        with self._backend._connect() as source_connection:
            draft = self._get(source_connection, source_key)
            if draft["revision"] != expected_revision or draft["assessment_stale"]:
                raise IntakeError("Email draft changed; refresh before update")
            original = draft["original"]
            assert isinstance(original, dict)
            event = _event(original)
            assessment = assess_email(event)
            if (
                not event.source.startswith("synthetic_")
                or assessment.kind != EmailKind.JOB_UPDATE
            ):
                raise IntakeError("Only synthetic job-update drafts can update jobs")
            facts = {fact.field: fact.value for fact in assessment.facts}
            supported = {
                "contactName",
                "email",
                "phone",
                "jobDescription",
                "requested_date",
            }
            if event.attachments or facts.keys() - supported - {
                "company",
                "siteLocation",
                "reference",
            }:
                raise IntakeError("Update evidence or scheduling fields require review")
            changes = {
                "preferredDate" if field == "requested_date" else field: value
                for field, value in facts.items()
                if field in supported
            }
            if not changes:
                raise IntakeError("Update has no supported canonical changes")
            reason = f"Synthetic email update: {source_key} {draft['source_hash']}"
            with requests._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                requests._source_schema(connection)
                receipts = connection.execute(
                    "SELECT request_id,decision_id,revision,content_hash,actor,"
                    "decided_at,decision,reason FROM intake_approvals "
                    "WHERE decision='source_changed' "
                    "AND reason=? LIMIT 2",
                    (reason,),
                ).fetchall()
                if receipts:
                    if len(receipts) != 1:
                        raise IntakeError("Update replay audit is inconsistent")
                    receipt = receipts[0]
                    _audit_row(connection, receipt[0], receipt[1:])
                    if requests._canonical(connection, receipt[0]) != receipt[0]:
                        raise IntakeError("Update replay target was relinked; review")
                    # Return current state: an old replay must not undo a later
                    # manual correction, approval, source update or cancellation.
                    return requests._get(connection, receipt[0])
                rows = connection.execute(
                    "SELECT request_id FROM intake_requests LIMIT 1001"
                ).fetchall()
                if len(rows) > 1000:
                    raise IntakeError("Update snapshot exceeds its bound")
                jobs = []
                for (identifier,) in rows:
                    job = requests._get(connection, identifier)
                    if requests._canonical(connection, identifier) == identifier:
                        jobs.append(job)
                proposal = match_email_job(event, assessment, jobs, complete=True)
                if proposal.status != "matched_proposal":
                    raise IntakeError("Update requires review: " + proposal.status)
                assert proposal.target_id is not None
                job = requests._get(connection, proposal.target_id)
                if (
                    job.revision != proposal.target_revision
                    or _digest(job.fields, job.attachments) != proposal.target_hash
                ):
                    raise IntakeError("Update target changed")
                fields = validate_fields({**job.fields, **changes})
                requests._record_revision(
                    connection,
                    job,
                    fields,
                    "source_changed",
                    reason,
                )
                return requests._get(connection, job.request_id)

    def list_drafts(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[tuple[dict[str, object], ...], int]:
        """Bounded queue with corrupt-row isolation and explicit failure count."""
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
        ):
            raise IntakeError("Invalid email draft page bounds")
        valid: list[dict[str, object]] = []
        malformed = 0
        with self._backend._connect() as connection:
            keys = connection.execute(
                "SELECT source_key FROM email_drafts ORDER BY rowid DESC "
                "LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            for (key,) in keys:
                try:
                    valid.append(self._get(connection, key))
                except IntakeError:
                    malformed += 1
        return tuple(valid), malformed

    def answer(
        self,
        source_key: str,
        revision: int,
        field: str,
        value: str,
        *,
        actor: str,
        requests: IntakeStore | None = None,
    ) -> dict[str, object]:
        self._backend._write()
        if field not in _ANSWER_FIELDS or type(revision) is not int:
            raise IntakeError("Invalid continuation field or revision")
        actor, value = _text(actor, 100), _text(value, 2000)
        if value.casefold().strip(" .") in _UNKNOWN:
            raise IntakeError("Answer is still unknown; leave the question unresolved")
        linked = False
        with self._backend._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._get(connection, source_key)
            if current["assessment_stale"]:
                raise IntakeError("Assessment upgrade requires audited reassessment")
            assessment = current["assessment"]
            assert isinstance(assessment, dict)
            if assessment["kind"] != EmailKind.NEW_JOB.value:
                raise IntakeError("Only a new-job draft can receive job answers")
            if current["revision"] != revision:
                raise IntakeError("Email draft changed; refresh before answering")
            if requests is not None:
                original = current["original"]
                assert isinstance(original, dict)
                linked = requests.stage_email_answer(
                    {
                        "source_system": "email",
                        "event_source": original["source"],
                        "source_account": original["source_account"],
                        "native_item_id": original["external_id"],
                    },
                    str(current["source_hash"]),
                    revision,
                    field,
                    value,
                )
            answers = current["answers"]
            history = current["history"]
            assert isinstance(answers, dict) and isinstance(history, list)
            previous = answers.get(field)
            answers[field] = {
                "value": value,
                "basis": "operator_confirmed",
                "actor": actor,
            }
            history.append(
                {
                    "revision": revision + 1,
                    "actor": actor,
                    "at": datetime.now(UTC).isoformat(),
                    "action": "answered",
                    "field": field,
                    "previous": previous,
                    "value": value,
                    "source_hash": current["source_hash"],
                }
            )
            connection.execute(
                "UPDATE email_drafts SET revision=?,answers=?,history=? "
                "WHERE source_key=?",
                (revision + 1, _json(answers), _json(history), source_key),
            )
            connection.commit()
            updated = self._get(connection, source_key)
        if linked and requests is not None:
            self.materialise(source_key, revision + 1, requests)
        return updated

    def reassess_synthetic(
        self, source_key: str, revision: int, *, actor: str
    ) -> dict[str, object]:
        """Audit synthetic assessment upgrades while retaining source and answers."""
        self._backend._write()
        actor = _text(actor, 100)
        with self._backend._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._get(connection, source_key)
            if type(revision) is not int or current["revision"] != revision:
                raise IntakeError("Email draft changed; refresh before reassessing")
            original = current["original"]
            history = current["history"]
            assert isinstance(original, dict) and isinstance(history, list)
            if not original["source"].startswith("synthetic_"):
                raise IntakeError(
                    "Real-store reassessment requires separate owner authority"
                )
            if not current["assessment_stale"]:
                return current
            assessment = _payload(assess_email(_event(original)))
            history.append(
                {
                    "revision": revision + 1,
                    "actor": actor,
                    "at": datetime.now(UTC).isoformat(),
                    "action": "reassessed",
                    "previous_assessment": current["assessment"],
                    "source_hash": current["source_hash"],
                }
            )
            connection.execute(
                "UPDATE email_drafts SET revision=?,assessment=?,history=? "
                "WHERE source_key=?",
                (revision + 1, _json(assessment), _json(history), source_key),
            )
            connection.commit()
            return self._get(connection, source_key)
