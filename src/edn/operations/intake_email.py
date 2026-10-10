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
_HISTORY = re.compile(
    r"^(?:On .+ wrote:|[- ]*(?:Original Message|Forwarded message)[- ]*|"
    r"Begin forwarded message:)",
    re.I,
)
_NEGATED = re.compile(
    r"\b(?:not a (?:new )?(?:work|job) request|"
    r"no (?:new )?(?:work|job) request|"
    r"no (?:attendance|booking|scheduling|action|further work) "
    r"(?:is )?(?:needed|required)|"
    r"(?:do not|don't|never|not to) (?:\w+\s+){0,3}"
    r"(?:cancel|install|repair|attend|replace|book|schedule))\b",
    re.I,
)
_UNKNOWN = frozenset({"tbc", "tbd", "unknown", "not known", "not provided", "n/a", "?"})
ASSESSMENT_VERSION = 4

_PREPARE_FORWARD = re.compile(
    r"Please (?:prepare|process) (?:the |this )?forwarded (?:work|job) request[.!]?",
    re.I,
)
_FORWARD_MARKER = re.compile(
    r"^(?:[- ]*Forwarded message[- ]*|Begin forwarded message:)$", re.I
)


def _requested_forward(body: str) -> tuple[str, str] | None:
    """Admit one explicitly requested forward, never arbitrary quoted history.

    Embedded From/To/Date are untrusted text, not identity or authorisation.
    Exactly one Subject and a blank header/body separator are required. Reply
    history, nested forwards and malformed headers leave the input uncertain.
    """
    lines = body.splitlines()
    markers = [i for i, line in enumerate(lines) if _HISTORY.match(line.strip())]
    if len(markers) != 1:
        return None
    index = markers[0]
    if not _FORWARD_MARKER.fullmatch(lines[index].strip()):
        return None
    if not _PREPARE_FORWARD.fullmatch("\n".join(lines[:index]).strip()):
        return None
    headers: dict[str, str] = {}
    tail = lines[index + 1 :]
    while tail and not tail[0].strip():
        tail = tail[1:]
    for offset, line in enumerate(tail):
        if not line.strip():
            if "subject" not in headers:
                return None
            content = "\n".join(tail[offset + 1 :])
            if not content.strip() or any(
                item.lstrip().startswith(">") for item in content.splitlines()
            ):
                return None
            return headers["subject"], content
        label, separator, value = line.partition(":")
        label = label.strip().lower()
        if (
            not separator
            or label not in {"from", "to", "date", "sent", "subject", "cc"}
            or label in headers
            or not value.strip()
        ):
            return None
        headers[label] = value.strip()
    return None


def _current_body(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if _HISTORY.match(line.strip()):
            break
        if not line.lstrip().startswith(">"):
            lines.append(line)
    return "\n".join(lines)


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
    current_body = _current_body(event.body)
    # Reply/forward subjects can describe an old job, not a current instruction.
    subject = (
        ""
        if re.match(r"^(?:re|fw|fwd):", event.subject.strip(), re.I)
        else event.subject
    )
    forwarded = _requested_forward(event.body)
    if forwarded is not None:
        # The strict outer instruction requests preparation, but is not proof
        # that the embedded sender, message IDs or contents are authentic.
        subject, current_body = forwarded
    text = subject + "\n" + current_body
    intent_text = text.replace("\u2019", "'").replace("\u2018", "'")
    matches = {kind for kind, pattern in _INTENTS if re.search(pattern, text, re.I)}
    # Quoted thread history is not reliable current intent. Any competing intent
    # requires review rather than guessing which sentence is authoritative.
    kind = next(iter(matches)) if len(matches) == 1 else EmailKind.UNCERTAIN
    if _NEGATED.search(intent_text):
        kind = EmailKind.UNCERTAIN
    if forwarded is not None and kind != EmailKind.NEW_JOB:
        kind = EmailKind.UNCERTAIN
    facts: list[EmailFact] = []
    conflicting: set[str] = set()
    for line in current_body.splitlines():
        label, separator, value = line.partition(":")
        field = _LABELS.get(label.strip().lower())
        value = value.strip()
        if not separator or field is None or not value:
            continue
        if value.casefold().strip(" .") in _UNKNOWN:
            conflicting.add(field)
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
    if forwarded is not None:
        reasons.append(
            "Explicitly requested single forward; embedded sender is unverified"
        )
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
