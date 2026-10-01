"""Entity-backed supporting-email candidates for the shared retrieval engine."""

from __future__ import annotations

from edn.knowledge_graph.persistence import KnowledgeGraphStore
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval.models import NormalizedQuery, RetrievalCandidate


class KnowledgeCandidateRetriever:
    """Resolve matching entities to their original supporting emails."""

    def __init__(
        self,
        graph_store: KnowledgeGraphStore,
        email_store: SQLiteEmailStore,
    ) -> None:
        self._graph_store = graph_store
        self._email_store = email_store

    def retrieve_candidates(
        self,
        query: NormalizedQuery,
        *,
        limit: int,
    ) -> tuple[RetrievalCandidate, ...]:
        source_keys = self._graph_store.source_keys_for_query(
            " ".join(query.terms), limit=limit
        )
        records = self._email_store.get_many(source_keys)
        return tuple(
            RetrievalCandidate(
                record=record,
                keyword_score=0.0,
                fts_rank=limit + rank,
                source_explanations=("knowledge entity support",),
            )
            for rank, record in enumerate(records, start=1)
        )
