"""Internal-only evidence-bound action planning and review."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from edn.intelligence.action_models import ActionProposal, ActionStatus
from edn.intelligence.models import AssembledContext

_SCHEMA = """
CREATE TABLE IF NOT EXISTS action_schema (
 component TEXT PRIMARY KEY, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS action_proposals (
 proposal_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL);
"""


class ActionProposalStore(Protocol):
    def create(self, proposal: ActionProposal) -> None: ...
    def get(self, proposal_id: str) -> ActionProposal | None: ...
    def review(
        self,
        proposal_id: str,
        *,
        status: ActionStatus,
        proposal_hash: str,
        human_review_ref: str,
        now: datetime,
        current_evidence_ids: tuple[str, ...],
    ) -> ActionProposal: ...


def proposal_fingerprint(proposal: ActionProposal) -> str:
    value = proposal.to_dict()
    for key in ("status", "proposal_hash", "human_review_ref"):
        value.pop(key)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _review(
    proposal: ActionProposal,
    status: ActionStatus,
    proposal_hash: str,
    human_review_ref: str,
    now: datetime,
    current_evidence_ids: tuple[str, ...],
) -> ActionProposal:
    if proposal_hash != proposal.proposal_hash:
        raise PermissionError("review does not match the exact proposal")
    if not human_review_ref.strip():
        raise ValueError("human review reference must not be blank")
    if status in {ActionStatus.EXECUTED, ActionStatus.FAILED}:
        raise PermissionError("external execution is not implemented or authorised")
    if status is ActionStatus.APPROVED_FOR_EXECUTION:
        if proposal.expires_at is not None and now >= proposal.expires_at:
            raise PermissionError("stale proposal requires renewed review")
        if not set(proposal.source_evidence_ids) <= set(current_evidence_ids):
            raise PermissionError("proposal evidence is no longer authorised")
    allowed = {
        ActionStatus.PROPOSED: {
            ActionStatus.DRAFT,
            ActionStatus.AWAITING_REVIEW,
            ActionStatus.REJECTED,
            ActionStatus.CANCELLED,
            ActionStatus.SUPERSEDED,
        },
        ActionStatus.DRAFT: {
            ActionStatus.AWAITING_REVIEW,
            ActionStatus.REJECTED,
            ActionStatus.CANCELLED,
            ActionStatus.SUPERSEDED,
        },
        ActionStatus.AWAITING_REVIEW: {
            ActionStatus.APPROVED_FOR_EXECUTION,
            ActionStatus.REJECTED,
            ActionStatus.CANCELLED,
            ActionStatus.SUPERSEDED,
        },
        ActionStatus.APPROVED_FOR_EXECUTION: {
            ActionStatus.CANCELLED,
            ActionStatus.SUPERSEDED,
        },
    }
    if status not in allowed.get(proposal.status, set()):
        raise ValueError("invalid internal action transition")
    return replace(proposal, status=status, human_review_ref=human_review_ref)


class InMemoryActionProposalStore:
    def __init__(self) -> None:
        self._items: dict[str, ActionProposal] = {}

    def create(self, proposal: ActionProposal) -> None:
        if proposal.proposal_id in self._items:
            raise ValueError("proposal ID already exists")
        self._items[proposal.proposal_id] = proposal

    def get(self, proposal_id: str) -> ActionProposal | None:
        return self._items.get(proposal_id)

    def review(
        self,
        proposal_id: str,
        *,
        status: ActionStatus,
        proposal_hash: str,
        human_review_ref: str,
        now: datetime,
        current_evidence_ids: tuple[str, ...],
    ) -> ActionProposal:
        proposal = self.get(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        proposal = _review(
            proposal,
            status,
            proposal_hash,
            human_review_ref,
            now,
            current_evidence_ids,
        )
        self._items[proposal_id] = proposal
        return proposal

    def revise(
        self,
        proposal_id: str,
        replacement: ActionProposal,
        *,
        proposal_hash: str,
        human_review_ref: str,
    ) -> ActionProposal:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError(proposal_id)
        self._items[proposal_id] = _review(
            current,
            ActionStatus.SUPERSEDED,
            proposal_hash,
            human_review_ref,
            current.created_at,
            current.source_evidence_ids,
        )
        if replacement.human_review_ref is not None:
            raise ValueError("modified proposal must not inherit approval")
        self.create(replacement)
        return replacement


class SQLiteActionProposalStore:
    def __init__(self, database_path: str | Path) -> None:
        self._path = Path(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialise(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT version FROM action_schema WHERE component = 'actions'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO action_schema(component, version) "
                    "VALUES ('actions', 1)"
                )
            elif int(row["version"]) != 1:
                raise RuntimeError("unsupported Intelligence Core action schema")

    def create(self, proposal: ActionProposal) -> None:
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO action_proposals VALUES (?, ?)",
                    (
                        proposal.proposal_id,
                        json.dumps(proposal.to_dict(), sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("proposal ID already exists") from error

    def get(self, proposal_id: str) -> ActionProposal | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM action_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
        return (
            None
            if row is None
            else ActionProposal.from_dict(json.loads(str(row["payload_json"])))
        )

    def review(
        self,
        proposal_id: str,
        *,
        status: ActionStatus,
        proposal_hash: str,
        human_review_ref: str,
        now: datetime,
        current_evidence_ids: tuple[str, ...],
    ) -> ActionProposal:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM action_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            proposal = ActionProposal.from_dict(json.loads(str(row["payload_json"])))
            proposal = _review(
                proposal,
                status,
                proposal_hash,
                human_review_ref,
                now,
                current_evidence_ids,
            )
            connection.execute(
                "UPDATE action_proposals SET payload_json = ? WHERE proposal_id = ?",
                (json.dumps(proposal.to_dict(), sort_keys=True), proposal_id),
            )
            return proposal

    def revise(
        self,
        proposal_id: str,
        replacement: ActionProposal,
        *,
        proposal_hash: str,
        human_review_ref: str,
    ) -> ActionProposal:
        if replacement.human_review_ref is not None:
            raise ValueError("modified proposal must not inherit approval")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM action_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(proposal_id)
            current = ActionProposal.from_dict(json.loads(str(row["payload_json"])))
            current = _review(
                current,
                ActionStatus.SUPERSEDED,
                proposal_hash,
                human_review_ref,
                current.created_at,
                current.source_evidence_ids,
            )
            connection.execute(
                "UPDATE action_proposals SET payload_json = ? WHERE proposal_id = ?",
                (json.dumps(current.to_dict(), sort_keys=True), proposal_id),
            )
            connection.execute(
                "INSERT INTO action_proposals VALUES (?, ?)",
                (
                    replacement.proposal_id,
                    json.dumps(replacement.to_dict(), sort_keys=True),
                ),
            )
            return replacement


@dataclass(slots=True)
class ActionPlanner:
    store: ActionProposalStore

    def plan(
        self,
        context: AssembledContext,
        *,
        now: datetime,
        include_draft: bool,
    ) -> ActionProposal | None:
        if not context.evidence:
            return None
        if now.tzinfo is None:
            raise ValueError("proposal time must be timezone-aware")
        evidence = context.evidence[0]
        request = context.request
        if any(
            ref.record.security_domain != request.security_domain
            or ref.record.classification != request.classification
            for ref in evidence.provenance
        ):
            raise PermissionError("proposal evidence exceeds request authority")
        capability = _target_capability(evidence.source_label)
        target = (
            evidence.provenance[0].record.source_uri
            or evidence.provenance[0].record.source_record_key
        )
        draft = None
        if include_draft:
            draft = (
                f"Subject: Follow-up — {evidence.title}\n\n"
                f"I am following up regarding {evidence.title}. "
                "Please confirm the current status, owner, and next decision."
            )
        proposal = ActionProposal(
            f"proposal-{uuid4().hex}",
            request.principal.principal_id,
            request.principal.tenant_id,
            request.security_domain.domain_id,
            (request.classification.scheme_id, request.classification.level_id),
            request.purpose.purpose_id,
            "prepare_follow_up",
            capability,
            target,
            (evidence.context_id,),
            evidence.excerpt,
            "evidence-backed",
            "Obtain a confirmed owner, status, and next decision.",
            "medium",
            "Internal draft is reversible; external execution is excluded.",
            f"{capability}.execute",
            "owner execution approval bound to exact proposal hash",
            draft,
            now,
            now + timedelta(days=7),
            ActionStatus.AWAITING_REVIEW if include_draft else ActionStatus.PROPOSED,
            "",
            None,
        )
        proposal = replace(proposal, proposal_hash=proposal_fingerprint(proposal))
        self.store.create(proposal)
        return proposal


def _target_capability(source_label: str) -> str:
    family = source_label.casefold()
    if "email" in family:
        return "email.send"
    if "calendar" in family:
        return "calendar.update"
    return "records.update"
