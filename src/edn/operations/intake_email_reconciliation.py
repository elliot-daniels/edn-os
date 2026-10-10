"""Source-bound job matching proposals, never inferred mutation authority."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from edn.operations.intake import (
    IntakeError,
    IntakeRequest,
    _attachments,
    _digest,
    validate_fields,
)
from edn.operations.intake_email import EmailAssessment, EmailKind, assess_email
from edn.operations.models import Event


@dataclass(frozen=True, slots=True)
class JobMatchProposal:
    status: str
    action: str
    source_key: str
    target_id: str | None = None
    target_revision: int | None = None
    target_hash: str | None = None
    candidate_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()


def _normalise(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 240
        or any(unicodedata.category(c).startswith("C") for c in value)
    ):
        raise IntakeError("Unsafe or missing matching evidence")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _job_hash(job: IntakeRequest) -> str:
    validate_fields(job.fields)
    _attachments(job.attachments, job.request_id)
    return _digest(job.fields, job.attachments)


def match_email_job(
    event: Event,
    assessment: EmailAssessment,
    jobs: Sequence[IntakeRequest],
    *,
    complete: bool = False,
) -> JobMatchProposal:
    """Require reference, customer and site agreement before proposing one target.

    Source facts are reported evidence, not verified customer authority. The
    caller supplies a complete canonical-store snapshot. This pure synthetic
    prerequisite neither imports a new job nor changes/cancels an existing one.
    """
    if not event.source.startswith("synthetic_"):
        raise IntakeError("Only synthetic reconciliation is permitted")
    if assessment.source_key != event.identity_key:
        raise IntakeError("Assessment belongs to another source")
    if not isinstance(jobs, (list, tuple)) or len(jobs) > 1000:
        raise IntakeError("Job reconciliation snapshot exceeds its bound")
    # Reject forged/stale assessments, including injected matches from quoted
    # history. Recompute with the current deterministic classifier.
    if assessment != assess_email(event):
        raise IntakeError("Assessment is stale or does not match source evidence")
    action = {
        EmailKind.NEW_JOB: "create_or_duplicate",
        EmailKind.JOB_UPDATE: "update",
        EmailKind.CANCELLATION: "cancel",
    }.get(assessment.kind)
    if action is None:
        return JobMatchProposal(
            "not_applicable",
            "none",
            event.identity_key,
            reasons=("Correspondence cannot mutate or schedule work",),
        )
    if type(complete) is not bool or not complete:
        return JobMatchProposal(
            "snapshot_unknown",
            action,
            event.identity_key,
            reasons=("Complete canonical job coverage has not been established",),
        )
    evidence = {fact.field: fact.value for fact in assessment.facts}
    required = ("reference", "company", "siteLocation")
    normalized = {}
    missing = []
    for name in required:
        try:
            normalized[name] = _normalise(evidence[name])
        except (KeyError, IntakeError):
            missing.append(name)
    if missing:
        return JobMatchProposal(
            "needs_information",
            action,
            event.identity_key,
            reasons=("Clarify only the missing or unsafe matching fields",),
            missing_fields=tuple(missing),
        )
    key = tuple(normalized[name] for name in required)
    candidates: list[tuple[IntakeRequest, str]] = []
    seen = set()
    try:
        for job in jobs:
            if (
                not isinstance(job, IntakeRequest)
                or str(UUID(job.request_id)) != job.request_id
                or job.request_id in seen
                or type(job.revision) is not int
                or job.revision < 1
                or job.state not in {"draft", "approved", "rejected", "cancelled"}
                or type(job.source_pending) is not bool
            ):
                raise ValueError
            seen.add(job.request_id)
            digest = _job_hash(job)
            if all(job.fields[name].strip() for name in required):
                job_key = tuple(_normalise(job.fields[name]) for name in required)
                if key == job_key:
                    candidates.append((job, digest))
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        # An invalid row could conceal another target; do not select a surviving
        # candidate and silently mutate the wrong job.
        raise IntakeError("Canonical job snapshot is malformed") from None
    ids = tuple(sorted(job.request_id for job, _ in candidates))
    if not candidates:
        return JobMatchProposal(
            "new_candidate" if action == "create_or_duplicate" else "unmatched",
            action,
            event.identity_key,
            reasons=("No existing job matches all three reported identifiers",),
        )
    if len(candidates) != 1:
        return JobMatchProposal(
            "ambiguous",
            action,
            event.identity_key,
            candidate_ids=ids,
            reasons=("Multiple jobs match; no target selected",),
        )
    job, digest = candidates[0]
    blocked = job.source_pending or job.state in {"rejected", "cancelled"}
    return JobMatchProposal(
        "needs_review" if blocked else "matched_proposal",
        action,
        event.identity_key,
        job.request_id,
        job.revision,
        digest,
        ids,
        ("Target is terminal or has unresolved source changes",)
        if blocked
        else (
            "Reported identifiers agree; execution still requires current-store guards",
        ),
    )
