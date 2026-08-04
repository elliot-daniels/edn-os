"""Provider-independent models for grounded EDN answers."""

from __future__ import annotations

from dataclasses import dataclass

from edn.retrieval.models import RetrievalEvidence

EmailEvidence = RetrievalEvidence


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
