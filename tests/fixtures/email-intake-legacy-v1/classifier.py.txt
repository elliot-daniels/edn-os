"""Source-bound email assessments. No provider, source read or booking action.

Extraction is deliberately conservative: labelled fields are facts reported by
the email, not verified customer records. Unstructured details remain available
in the immutable Event for a separately governed extraction adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from edn.operations.models import Event


class EmailKind(StrEnum):
    NEW_JOB = "new_job"
    JOB_UPDATE = "job_update"
    CANCELLATION = "cancellation"
    FOLLOW_UP = "follow_up"
    FINANCIAL = "financial_correspondence"
    INFORMATION = "general_information"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class EmailFact:
    field: str
    value: str
    quote: str
    source_key: str
    basis: str = "email_reported"


@dataclass(frozen=True, slots=True)
class MissingQuestion:
    field: str
    category: str
    question: str


@dataclass(frozen=True, slots=True)
class EmailAssessment:
    source_key: str
    kind: EmailKind
    facts: tuple[EmailFact, ...]
    questions: tuple[MissingQuestion, ...]
    reasons: tuple[str, ...]

    @property
    def prepares_new_job(self) -> bool:
        return self.kind == EmailKind.NEW_JOB


_LABELS = {
    "customer": "company",
    "contact": "contactName",
    "email": "email",
    "phone": "phone",
    "site": "siteLocation",
    "scope": "jobDescription",
    "job reference": "reference",
    "equipment": "equipment",
    "requested date": "requested_date",
    "requested time": "requested_time",
    "duration": "duration",
    "access": "access_requirements",
}
_QUESTIONS = (
    ("siteLocation", "before_scheduling", "Where will the work take place?"),
    ("jobDescription", "before_scheduling", "What work is required?"),
    ("duration", "before_scheduling", "How long should the work take?"),
    ("contactName", "before_attending", "Who is the site contact?"),
    ("access_requirements", "before_attending", "What access arrangements apply?"),
    ("company", "before_invoicing", "Which customer should be invoiced?"),
    ("reference", "before_invoicing", "Is a purchase order or job reference required?"),
    ("equipment", "optional", "Is any equipment specified?"),
)
_INTENTS = (
    (
        EmailKind.CANCELLATION,
        r"\b(?:cancel (?:the |this )?(?:job|booking)|job cancelled)\b",
    ),
    (
        EmailKind.JOB_UPDATE,
        r"\b(?:reschedule (?:the |this )?job|job update|change of scope)\b",
    ),
    (
        EmailKind.NEW_JOB,
        r"\b(?:new work request|new job request|"
        r"please (?:install|repair|attend|replace))\b",
    ),
    (EmailKind.FOLLOW_UP, r"\b(?:following up|follow.up|any update)\b"),
    (
        EmailKind.FINANCIAL,
        r"\b(?:invoice|remittance|payment received|statement of account)\b",
    ),
    (
        EmailKind.INFORMATION,
        r"\b(?:for your information|fyi|newsletter|general information)\b",
    ),
)


def assess_email(event: Event) -> EmailAssessment:
    """Bounded local baseline; ambiguity never grants scheduling authority.

    Forwarded text may carry useful facts but cannot supply trusted identity or
    a link to another job. Linking, replay and reservations belong to the durable
    workflow, not this classifier. Cancellation/update/follow-up cannot create
    new jobs, even when a thread contains old new-job wording.
    """
    if event.event_type != "email" or event.direction != "inbound":
        raise ValueError("Assessment requires an inbound Operations email")
    if len(event.subject) + len(event.body) > 100_000:
        raise ValueError("Email assessment exceeds bounded text limit")
    text = event.subject + "\n" + event.body
    matches = {kind for kind, pattern in _INTENTS if re.search(pattern, text, re.I)}
    # Quoted thread history is not reliable current intent. Any competing intent
    # requires review rather than guessing which sentence is authoritative.
    kind = next(iter(matches)) if len(matches) == 1 else EmailKind.UNCERTAIN
    facts: list[EmailFact] = []
    conflicting: set[str] = set()
    for line in event.body.splitlines():
        label, separator, value = line.partition(":")
        field = _LABELS.get(label.strip().lower())
        value = value.strip()
        if not separator or field is None or not value:
            continue
        if len(value) > 2000 or any(ord(char) < 32 for char in value):
            conflicting.add(field)
            continue
        previous = next((fact for fact in facts if fact.field == field), None)
        if previous is not None:
            if previous.value != value:
                conflicting.add(field)
            continue
        facts.append(EmailFact(field, value, line, event.identity_key))
    facts = [fact for fact in facts if fact.field not in conflicting]
    known = {fact.field for fact in facts}
    questions = tuple(
        MissingQuestion(field, category, question)
        for field, category, question in _QUESTIONS
        if field not in known and kind == EmailKind.NEW_JOB
    )
    reasons = ["Local conservative rules; no external AI processing"]
    if kind == EmailKind.UNCERTAIN:
        reasons.append("Missing or competing intent; no automatic job or booking")
    if conflicting:
        reasons.append(
            "Conflicting fields require clarification: "
            + ", ".join(sorted(conflicting))
        )
    return EmailAssessment(
        event.identity_key, kind, tuple(facts), questions, tuple(reasons)
    )
