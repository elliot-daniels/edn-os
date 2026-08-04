"""Deterministic natural-language query normalization."""

from __future__ import annotations

import re
from collections.abc import Sequence

from edn.retrieval.models import NormalizedQuery

MAX_SEARCH_TERMS = 12
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._@:/-][A-Za-z0-9]+)*")
_QUOTED_PATTERN = re.compile(r'["“”]([^"“”]+)["“”]')
_TICKET_PATTERN = re.compile(r"(?i)\b[A-Z]{2,12}[-_]\d{2,}\b")
_HOSTNAME_PATTERN = re.compile(
    r"(?i)\b(?=[A-Z0-9._-]*[A-Z])(?=[A-Z0-9._-]*\d)[A-Z0-9]+(?:[._-][A-Z0-9]+)*\b"
)
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
        "examples",
        "explain",
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
        "show",
        "tell",
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


def _singularize(term: str) -> str:
    """Apply deliberately conservative English plural normalization."""
    if not term.isalpha() or not term.islower() or len(term) < 5:
        return term
    if term.endswith("ies") and len(term) > 5:
        return term[:-3] + "y"
    if term.endswith("ses") or term.endswith("xes") or term.endswith("zes"):
        return term[:-2]
    if term.endswith("s") and not term.endswith(("ss", "us", "is")):
        return term[:-1]
    return term


def _safe_phrase(value: str) -> str:
    return " ".join(match.group(0) for match in _TOKEN_PATTERN.finditer(value))


def _deduplicate(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _deduplicate_identifiers(values: Sequence[str]) -> tuple[str, ...]:
    """Prefer complete identifiers over ticket-like substrings within them."""
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if any(key in existing.casefold() for existing in result):
            continue
        result = [existing for existing in result if existing.casefold() not in key]
        result.append(value)
    return tuple(result)


def build_fts_query(terms: Sequence[str], phrases: Sequence[str] = ()) -> str:
    """Build an OR-only FTS query from locally tokenized values."""
    components: list[str] = []
    for phrase in phrases:
        safe = _safe_phrase(phrase)
        if safe:
            components.append(f'"{safe}"')
    for term in terms:
        if _TOKEN_PATTERN.fullmatch(term):
            components.append(f'"{term}"')
    return " OR ".join(_deduplicate(components))


def normalize_query(question: str) -> NormalizedQuery:
    """Normalize a question without exposing raw FTS operators or syntax."""
    normalized_question = " ".join(question.split())
    phrases = _deduplicate(
        tuple(
            safe
            for match in _QUOTED_PATTERN.finditer(normalized_question)
            if (safe := _safe_phrase(match.group(1)))
        )
    )

    terms: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(normalized_question):
        raw_term = match.group(0)
        comparison = raw_term.casefold()
        if comparison in _STOP_WORDS:
            continue
        term = (
            raw_term
            if any(character.isupper() for character in raw_term)
            else comparison
        )
        term = _singularize(term)
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
        if len(terms) == MAX_SEARCH_TERMS:
            break

    acronyms = _deduplicate(
        tuple(
            term
            for term in terms
            if term.isupper() and term.isalpha() and len(term) >= 2
        )
    )
    identifiers = _deduplicate_identifiers(
        tuple(_HOSTNAME_PATTERN.findall(normalized_question))
        + tuple(_TICKET_PATTERN.findall(normalized_question))
    )
    normalized_terms = tuple(terms)
    return NormalizedQuery(
        original=normalized_question,
        terms=normalized_terms,
        phrases=phrases,
        acronyms=acronyms,
        identifiers=identifiers,
        fts_query=build_fts_query(normalized_terms, phrases),
    )
