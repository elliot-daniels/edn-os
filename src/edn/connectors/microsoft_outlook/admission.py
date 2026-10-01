"""Metadata-only Email Admission V2 over explicitly supplied verified snapshots.

This module has no clients, credentials, discovery or ranking. A snapshot is an
owner-approved input, not a relationship inferred from mailbox contents.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from edn.connectors.admission import (
    AdmissionDecision,
    AdmissionOutcome,
    AdmissionSourceCoverage,
)
from edn.core import Classification, EvidenceRef, SecurityDomain
from edn.core.security import validate_identifier


class RelationshipState(StrEnum):
    RETRIEVED = "retrieved"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    PARTIAL = "partial"
    MALFORMED = "malformed"


class RelationshipSignal(StrEnum):
    CLIENT_SENDER = "verified_client_sender"
    EDN_SENDER = "verified_edn_sender"
    PROJECT_REFERENCE = "verified_project_reference"


def address(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}",
        value,
    ):
        raise ValueError("malformed email address")
    local, domain = value.rsplit("@", 1)
    # Preserve local-part case. Do not infer alias/plus-address equivalence.
    return local + "@" + domain.lower()


@dataclass(frozen=True, slots=True)
class VerifiedRelationship:
    signal: RelationshipSignal
    value: str
    entity_id: str
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        if not isinstance(self.signal, RelationshipSignal) or not self.entity_id:
            raise ValueError("relationship signal and exact entity required")
        if self.signal is RelationshipSignal.PROJECT_REFERENCE:
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,63}", self.value):
                raise ValueError(
                    "project reference requires an explicit canonical code"
                )
        elif address(self.value) != self.value:
            raise ValueError("relationship address must use canonical domain case")


@dataclass(frozen=True, slots=True)
class RelationshipSnapshot:
    source_id: str
    state: RelationshipState
    checked_at: datetime | None
    relationships: tuple[VerifiedRelationship, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.source_id, "relationship_source")
        if not isinstance(self.state, RelationshipState):
            raise ValueError("unknown relationship state")
        if self.checked_at is not None and self.checked_at.tzinfo is None:
            raise ValueError("relationship check must be timezone-aware")
        if self.state is RelationshipState.EMPTY and self.relationships:
            raise ValueError("empty source cannot contain relationships")
        if self.state is RelationshipState.RETRIEVED and not self.relationships:
            raise ValueError("use empty state for a checked empty source")


@dataclass(frozen=True, slots=True)
class EmailAdmissionPolicy:
    security_domain: SecurityDomain
    classification: Classification
    snapshots: tuple[RelationshipSnapshot, ...]
    max_age: timedelta = timedelta(days=1)
    category: str = "EDN"

    def __post_init__(self) -> None:
        if self.category != "EDN" or self.max_age <= timedelta(0):
            raise ValueError(
                "explicit EDN category and positive freshness bound required"
            )
        if len({s.source_id for s in self.snapshots}) != len(self.snapshots):
            raise ValueError("relationship source instances must be unique")
        if not {"clients", "projects"} <= {s.source_id for s in self.snapshots}:
            raise ValueError("declare clients/projects coverage, including unavailable")
        for snapshot in self.snapshots:
            for relation in snapshot.relationships:
                record = relation.evidence.record
                if (
                    record.security_domain != self.security_domain
                    or record.classification != self.classification
                ):
                    raise ValueError(
                        "relationship evidence exceeds the admission domain"
                    )

    @property
    def authority_id(self) -> str:
        # Exact policy AND snapshots are covered by the permission grant. Replacing
        # relationship evidence cannot silently reuse an older admission authority.
        payload = asdict(self)
        payload["snapshots"] = sorted(
            payload["snapshots"], key=lambda s: s["source_id"]
        )
        encoded = json.dumps(
            payload, default=str, sort_keys=True, separators=(",", ":")
        )
        return "email-admission-v2:" + hashlib.sha256(encoded.encode()).hexdigest()

    def coverage(self, now: datetime) -> tuple[str, ...]:
        if now.tzinfo is None:
            raise ValueError("admission clock must be timezone-aware")
        return tuple(sorted(filter(None, (self._gap(s, now) for s in self.snapshots))))

    def source_coverage(self, now: datetime) -> tuple[AdmissionSourceCoverage, ...]:
        self.coverage(now)
        return tuple(
            AdmissionSourceCoverage(
                s.source_id,
                self._gap(s, now) or s.state.value,
                s.checked_at,
                len(s.relationships),
            )
            for s in sorted(self.snapshots, key=lambda s: s.source_id)
        )

    def _gap(self, snapshot: RelationshipSnapshot, now: datetime) -> str:
        state = snapshot.state
        if state not in {RelationshipState.RETRIEVED, RelationshipState.EMPTY}:
            return f"relationship_{snapshot.source_id}_{state.value}"
        checked = snapshot.checked_at
        if checked is None or checked > now:
            return f"relationship_{snapshot.source_id}_freshness_unknown"
        if now - checked > self.max_age:
            return f"relationship_{snapshot.source_id}_stale"
        return ""

    def decide(self, metadata: dict[str, Any], *, now: datetime) -> AdmissionDecision:
        gaps = self.coverage(now)
        key = metadata.get("id")
        key = key if isinstance(key, str) and key else "unidentified"

        def result(
            outcome: AdmissionOutcome,
            *reasons: str,
            evidence: tuple[EvidenceRef, ...] = (),
        ) -> AdmissionDecision:
            return AdmissionDecision(
                key, self.authority_id, outcome, tuple(reasons), evidence
            )

        try:
            if key == "unidentified" or any(ord(c) < 32 for c in key):
                raise ValueError("missing identifier")
            sender = address(metadata["from"]["emailAddress"]["address"])
            recipients = metadata["toRecipients"]
            categories = metadata["categories"]
            subject = metadata["subject"]
            if not isinstance(recipients, list) or not isinstance(categories, list):
                raise ValueError("malformed collection")
            for recipient in recipients:
                address(recipient["emailAddress"]["address"])
            if any(not isinstance(c, str) for c in categories) or not isinstance(
                subject, str
            ):
                raise ValueError("malformed metadata")
        except (KeyError, TypeError, ValueError):
            return result(AdmissionOutcome.REJECTED, "malformed_metadata")
        matches: list[VerifiedRelationship] = []
        by_signal: dict[tuple[str, str], set[str]] = {}
        for snapshot in self.snapshots:
            if self._gap(snapshot, now):
                continue  # Partial snapshots cannot prove a unique relationship.
            for relation in snapshot.relationships:
                matched = (
                    f"[PROJECT:{relation.value}]" in subject
                    if relation.signal is RelationshipSignal.PROJECT_REFERENCE
                    else sender == relation.value
                )
                if matched:
                    matches.append(relation)
                    by_signal.setdefault(
                        (relation.signal.value, relation.value), set()
                    ).add(relation.entity_id)
        if any(len(entities) > 1 for entities in by_signal.values()):
            return result(AdmissionOutcome.REJECTED, "ambiguous_relationship")
        if self.category in categories:
            return result(AdmissionOutcome.ADMITTED, "explicit_edn_category")
        if matches:
            refs = {r.evidence.to_json(): r.evidence for r in matches}
            return result(
                AdmissionOutcome.ADMITTED,
                *sorted({r.signal.value for r in matches}),
                evidence=tuple(refs[key] for key in sorted(refs)),
            )
        if gaps:
            return result(
                AdmissionOutcome.UNAVAILABLE, "relationship_evidence_unavailable", *gaps
            )
        return result(AdmissionOutcome.REJECTED, "no_edn_relevance_signal")
