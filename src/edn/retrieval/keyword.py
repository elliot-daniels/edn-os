"""Bounded FTS5 candidate retrieval."""

from __future__ import annotations

from typing import Protocol

from edn.memory.storage import SQLiteEmailStore
from edn.retrieval.models import NormalizedQuery, RetrievalCandidate


class CandidateRetriever(Protocol):
    """Backend boundary used by the retrieval engine."""

    def retrieve_candidates(
        self,
        query: NormalizedQuery,
        *,
        limit: int,
    ) -> tuple[RetrievalCandidate, ...]:
        """Return at most limit candidates without scanning the full corpus."""


class SQLiteFTSKeywordRetriever:
    """Adapt SQLite FTS5 results into backend-neutral candidates."""

    def __init__(self, store: SQLiteEmailStore) -> None:
        self._store = store

    def retrieve_candidates(
        self,
        query: NormalizedQuery,
        *,
        limit: int,
    ) -> tuple[RetrievalCandidate, ...]:
        if not query.fts_query:
            return ()
        ranked = self._store.search_ranked(query.fts_query, limit=limit)
        return tuple(
            RetrievalCandidate(
                record=item.record,
                keyword_score=item.fts_score,
                fts_rank=item.fts_rank,
            )
            for item in ranked
        )
