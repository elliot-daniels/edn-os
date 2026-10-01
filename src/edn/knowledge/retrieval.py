"""Compatibility wrappers for the core retrieval service."""

from __future__ import annotations

from collections.abc import Sequence

from edn.knowledge.models import EmailEvidence
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval.engine import (
    DEFAULT_EVIDENCE_LIMIT,
    DEFAULT_EXCERPT_CHARACTERS,
    RetrievalEngine,
    RetrievalError,
)
from edn.retrieval.query import build_fts_query as _build_fts_query
from edn.retrieval.query import normalize_query

EvidenceRetrievalError = RetrievalError


def question_to_search_terms(question: str) -> tuple[str, ...]:
    """Return normalized terms for callers using the Module 002.3 API."""
    return tuple(term.casefold() for term in normalize_query(question).terms[:8])


def build_fts_query(terms: Sequence[str]) -> str:
    """Build a safe legacy OR query from already tokenized terms."""
    return _build_fts_query(terms)


def retrieve_email_evidence(
    question: str,
    store: SQLiteEmailStore,
    *,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    excerpt_characters: int = DEFAULT_EXCERPT_CHARACTERS,
) -> tuple[EmailEvidence, ...]:
    """Delegate the legacy API to the shared retrieval engine."""
    return RetrievalEngine.from_store(
        store,
        excerpt_characters=excerpt_characters,
    ).retrieve(
        question,
        limit=limit,
    )
