"""Provider-independent models for grounded EDN answers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EmailEvidence:
    """One ranked email supplied as evidence to an answer provider."""

    evidence_id: int
    source_record_key: str
    subject: str
    sender: str
    sent_at: datetime | None
    folder_path: str
    message_id: str | None
    body_excerpt: str
    body_text: str


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    """An answer whose citations must resolve to retrieved evidence."""

    text: str
    cited_evidence_ids: tuple[int, ...]
    insufficient_evidence: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnsweredQuestion:
    """A validated answer paired with its ranked retrieved evidence."""

    answer: GroundedAnswer
    evidence: tuple[EmailEvidence, ...]
