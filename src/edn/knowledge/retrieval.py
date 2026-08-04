"""Deterministic and FTS-safe email evidence retrieval."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence

from edn.knowledge.models import EmailEvidence
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore

DEFAULT_EVIDENCE_LIMIT = 5
MAX_EVIDENCE_LIMIT = 10
DEFAULT_EXCERPT_CHARACTERS = 600
MAX_SEARCH_TERMS = 8

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._@-][A-Za-z0-9]+)*")
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "at",
        "be",
        "did",
        "do",
        "during",
        "for",
        "from",
        "happened",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "or",
        "our",
        "the",
        "there",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


class EvidenceRetrievalError(RuntimeError):
    """Raised when email evidence cannot be retrieved safely."""


def question_to_search_terms(question: str) -> tuple[str, ...]:
    """Extract bounded, unique FTS-safe terms from a natural-language question."""
    terms: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(question.casefold()):
        term = match.group(0)
        if term in _STOP_WORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) == MAX_SEARCH_TERMS:
            break
    return tuple(terms)


def build_fts_query(terms: Sequence[str]) -> str:
    """Build an OR query from terms that have already passed local tokenization."""
    safe_terms = [term for term in terms if _TOKEN_PATTERN.fullmatch(term)]
    return " OR ".join(f'"{term}"' for term in safe_terms)


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


def _to_evidence(
    record: EmailRecord,
    evidence_id: int,
    terms: Sequence[str],
    *,
    excerpt_characters: int,
) -> EmailEvidence:
    return EmailEvidence(
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
            max_characters=excerpt_characters,
        ),
        body_text=record.body_text,
    )


def retrieve_email_evidence(
    question: str,
    store: SQLiteEmailStore,
    *,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    excerpt_characters: int = DEFAULT_EXCERPT_CHARACTERS,
) -> tuple[EmailEvidence, ...]:
    """Retrieve ranked email evidence without passing raw questions to FTS5."""
    if not 1 <= limit <= MAX_EVIDENCE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_EVIDENCE_LIMIT}")
    if excerpt_characters < 20:
        raise ValueError("excerpt_characters must be at least 20")

    terms = question_to_search_terms(question)
    fts_query = build_fts_query(terms)
    if not fts_query:
        return ()

    try:
        records = store.search(fts_query, limit=limit)
    except sqlite3.Error as error:
        raise EvidenceRetrievalError(
            "Email evidence could not be retrieved from the local index."
        ) from error

    return tuple(
        _to_evidence(
            record,
            evidence_id,
            terms,
            excerpt_characters=excerpt_characters,
        )
        for evidence_id, record in enumerate(records, start=1)
    )
