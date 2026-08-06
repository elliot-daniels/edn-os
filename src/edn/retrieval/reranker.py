"""Configurable deterministic reranking for bounded retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from edn.retrieval.models import NormalizedQuery, RetrievalCandidate, ScoredCandidate


@dataclass(frozen=True, slots=True)
class RerankWeights:
    """Central scoring configuration; zero disables an individual signal."""

    keyword_rank: float = 2.0
    subject_match: float = 2.5
    sender_match: float = 1.25
    folder_match: float = 0.75
    body_term: float = 0.15
    body_term_cap: float = 1.5
    exact_phrase: float = 4.0
    acronym: float = 1.5
    identifier: float = 3.0
    knowledge_match: float = 3.0
    recent: float = 0.5
    recent_window_days: int = 365


class DeterministicReranker:
    """Combine transparent lexical and metadata signals with FTS rank."""

    def __init__(self, weights: RerankWeights | None = None) -> None:
        self.weights = weights or RerankWeights()

    def rerank(
        self,
        query: NormalizedQuery,
        candidates: tuple[RetrievalCandidate, ...],
    ) -> tuple[ScoredCandidate, ...]:
        newest = max(
            (item.record.sent_at for item in candidates if item.record.sent_at),
            default=None,
        )
        scored = tuple(
            self._score(query, candidate, newest) for candidate in candidates
        )
        return tuple(
            sorted(
                scored,
                key=lambda item: (
                    -item.score,
                    item.candidate.fts_rank,
                    item.candidate.record.source_record_key,
                ),
            )
        )

    def _score(
        self,
        query: NormalizedQuery,
        candidate: RetrievalCandidate,
        newest: datetime | None,
    ) -> ScoredCandidate:
        record = candidate.record
        subject = record.subject.casefold()
        sender = record.sender.casefold()
        folder = record.folder_path.casefold()
        body = record.body_text.casefold()
        terms = tuple(term.casefold() for term in query.terms)
        explanations = list(candidate.source_explanations)
        score = self.weights.keyword_rank / max(candidate.fts_rank, 1)
        explanations.append(f"keyword rank {candidate.fts_rank}")
        if candidate.source_explanations:
            score += self.weights.knowledge_match

        def add_signal(label: str, amount: float) -> None:
            nonlocal score
            score += amount
            explanations.append(label)

        subject_matches = sum(term in subject for term in terms)
        if subject_matches:
            add_signal(
                f"subject match {subject_matches}",
                self.weights.subject_match * subject_matches,
            )
        if any(term in sender for term in terms):
            add_signal("sender match", self.weights.sender_match)
        if any(term in folder for term in terms):
            add_signal("folder match", self.weights.folder_match)

        frequency = sum(body.count(term) for term in terms)
        if frequency:
            body_score = min(
                frequency * self.weights.body_term,
                self.weights.body_term_cap,
            )
            add_signal(f"body frequency {frequency}", body_score)

        searchable_text = "\n".join(
            (record.subject, record.sender, record.folder_path, record.body_text)
        ).casefold()
        derived_phrases = tuple(
            " ".join(terms[index : index + 2])
            for index in range(max(0, len(terms) - 1))
        )
        ranking_phrases = query.phrases + derived_phrases
        matched_phrases = [
            phrase for phrase in ranking_phrases if phrase.casefold() in searchable_text
        ]
        if matched_phrases:
            add_signal("exact phrase", self.weights.exact_phrase)
        if any(acronym.casefold() in searchable_text for acronym in query.acronyms):
            add_signal("acronym match", self.weights.acronym)
        if any(
            identifier.casefold() in searchable_text for identifier in query.identifiers
        ):
            add_signal("identifier match", self.weights.identifier)

        if newest is not None and record.sent_at is not None:
            threshold = newest - timedelta(days=self.weights.recent_window_days)
            if record.sent_at >= threshold:
                add_signal("recent", self.weights.recent)

        rerank_score = score - self.weights.keyword_rank / max(candidate.fts_rank, 1)
        return ScoredCandidate(
            candidate=candidate,
            rerank_score=rerank_score,
            score=score,
            explanations=tuple(explanations),
        )
