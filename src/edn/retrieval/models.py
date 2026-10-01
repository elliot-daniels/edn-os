"""Provider-independent models for the EDN retrieval pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from edn.memory.models import EmailRecord


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    """A natural-language question converted to bounded FTS-safe components."""

    original: str
    terms: tuple[str, ...]
    phrases: tuple[str, ...]
    acronyms: tuple[str, ...]
    identifiers: tuple[str, ...]
    fts_query: str


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """A bounded backend candidate ready for deterministic reranking."""

    record: EmailRecord
    keyword_score: float
    fts_rank: int
    semantic_score: float | None = None
    source_explanations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    """A candidate with its deterministic score and explanations."""

    candidate: RetrievalCandidate
    rerank_score: float
    score: float
    explanations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEvidence:
    """One ranked, attributable email returned by the retrieval service."""

    evidence_id: int
    source_record_key: str
    subject: str
    sender: str
    sent_at: datetime | None
    folder_path: str
    message_id: str | None
    body_excerpt: str
    body_text: str
    score: float = 0.0
    fts_rank: int = 0
    keyword_score: float = 0.0
    rerank_score: float = 0.0
    semantic_score: float | None = None
    explanations: tuple[str, ...] = ()

    @property
    def body_reference(self) -> str:
        """Return the stable reference used to resolve the full source body."""
        return self.source_record_key
