"""Provider-neutral orchestration for ranked, explainable evidence retrieval."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from edn.memory.storage import DatabaseBusyError, SQLiteEmailStore
from edn.retrieval.keyword import CandidateRetriever, SQLiteFTSKeywordRetriever
from edn.retrieval.models import RetrievalEvidence, ScoredCandidate
from edn.retrieval.query import normalize_query
from edn.retrieval.reranker import DeterministicReranker

DEFAULT_EVIDENCE_LIMIT = 5
MAX_EVIDENCE_LIMIT = 10
DEFAULT_CANDIDATE_LIMIT = 20
DEFAULT_EXCERPT_CHARACTERS = 600


class RetrievalError(RuntimeError):
    """Raised when evidence cannot be retrieved without exposing internals."""


def _normalized_excerpt(
    body_text: str,
    terms: Sequence[str],
    *,
    max_characters: int,
) -> str:
    normalized = " ".join(body_text.split())
    if not normalized:
        return "(No plain-text body)"
    if len(normalized) <= max_characters:
        return normalized
    lower_body = normalized.casefold()
    positions = [lower_body.find(term.casefold()) for term in terms]
    matching_positions = [position for position in positions if position >= 0]
    center = min(matching_positions) if matching_positions else 0
    start = max(0, center - max_characters // 3)
    end = min(len(normalized), start + max_characters)
    start = max(0, end - max_characters)
    excerpt = normalized[start:end].strip()
    if start > 0:
        excerpt = "…" + excerpt[1:]
    if end < len(normalized):
        excerpt = excerpt[:-1] + "…"
    return excerpt


class RetrievalEngine:
    """Stable facade for current keyword and future semantic retrieval."""

    def __init__(
        self,
        keyword_retriever: CandidateRetriever,
        *,
        reranker: DeterministicReranker | None = None,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
        excerpt_characters: int = DEFAULT_EXCERPT_CHARACTERS,
    ) -> None:
        if candidate_limit < 1:
            raise ValueError("candidate_limit must be at least 1")
        if excerpt_characters < 20:
            raise ValueError("excerpt_characters must be at least 20")
        self._keyword_retriever = keyword_retriever
        self._reranker = reranker or DeterministicReranker()
        self._candidate_limit = candidate_limit
        self._excerpt_characters = excerpt_characters

    @classmethod
    def from_store(
        cls,
        store: SQLiteEmailStore,
        *,
        reranker: DeterministicReranker | None = None,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
        excerpt_characters: int = DEFAULT_EXCERPT_CHARACTERS,
    ) -> RetrievalEngine:
        """Compose the engine with the existing SQLite FTS5 backend."""
        return cls(
            SQLiteFTSKeywordRetriever(store),
            reranker=reranker,
            candidate_limit=candidate_limit,
            excerpt_characters=excerpt_characters,
        )

    def retrieve(
        self,
        question: str,
        *,
        limit: int = DEFAULT_EVIDENCE_LIMIT,
    ) -> tuple[RetrievalEvidence, ...]:
        """Return bounded, reranked evidence through a stable service API."""
        if not 1 <= limit <= MAX_EVIDENCE_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_EVIDENCE_LIMIT}")
        query = normalize_query(question)
        if not query.fts_query:
            return ()
        try:
            candidates = self._keyword_retriever.retrieve_candidates(
                query,
                limit=max(limit, self._candidate_limit),
            )
        except DatabaseBusyError as error:
            raise RetrievalError(
                "The local email database is temporarily busy. Try again shortly."
            ) from error
        except sqlite3.Error as error:
            raise RetrievalError(
                "Email evidence could not be retrieved from the local index."
            ) from error
        ranked = self._reranker.rerank(query, candidates)[:limit]
        return tuple(
            self._to_evidence(item, evidence_id, query.terms)
            for evidence_id, item in enumerate(ranked, start=1)
        )

    def _to_evidence(
        self,
        item: ScoredCandidate,
        evidence_id: int,
        terms: Sequence[str],
    ) -> RetrievalEvidence:
        candidate = item.candidate
        record = candidate.record
        return RetrievalEvidence(
            evidence_id=evidence_id,
            source_record_key=record.source_record_key,
            subject=record.subject,
            sender=record.sender,
            sent_at=record.sent_at,
            folder_path=record.folder_path,
            message_id=record.message_id,
            body_excerpt=_normalized_excerpt(
                record.body_text,
                terms,
                max_characters=self._excerpt_characters,
            ),
            body_text=record.body_text,
            score=item.score,
            fts_rank=candidate.fts_rank,
            keyword_score=candidate.keyword_score,
            rerank_score=item.rerank_score,
            semantic_score=candidate.semantic_score,
            explanations=item.explanations,
        )
