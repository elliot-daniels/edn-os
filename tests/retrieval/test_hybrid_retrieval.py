"""Synthetic tests for query normalization and deterministic hybrid ranking."""

from datetime import UTC, datetime
from pathlib import Path

from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.retrieval import RetrievalEngine
from edn.retrieval.models import RetrievalCandidate
from edn.retrieval.query import normalize_query
from edn.retrieval.reranker import DeterministicReranker, RerankWeights


def _record(
    key: str,
    *,
    subject: str,
    body: str,
    sender: str = "engineer@example.com",
    folder: str = "Inbox/Operations",
    year: int = 2026,
) -> EmailRecord:
    return EmailRecord(
        source_record_key=key,
        folder_path=folder,
        subject=subject,
        sender=sender,
        recipients_to=("operator@example.com",),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=datetime(year, 7, 18, tzinfo=UTC),
        received_at=None,
        message_id=f"<{key}@example.com>",
        body_text=body,
    )


def _engine(tmp_path: Path, records: tuple[EmailRecord, ...]) -> RetrievalEngine:
    store = SQLiteEmailStore(tmp_path / "memory.db")
    store.initialise()
    store.add_many(records)
    return RetrievalEngine.from_store(store, candidate_limit=20)


def test_normalization_handles_noise_plural_and_whitespace() -> None:
    query = normalize_query("  Tell me about   MX304 upgrades?! ")

    assert query.terms == ("MX304", "upgrade")
    assert query.identifiers == ("MX304",)
    assert query.fts_query == '"MX304" OR "upgrade"'


def test_normalization_preserves_quoted_phrase_and_acronym() -> None:
    query = normalize_query('What did NOC do for "Pimba outage"?')

    assert query.phrases == ("Pimba outage",)
    assert query.acronyms == ("NOC",)
    assert query.fts_query.startswith('"Pimba outage" OR')


def test_malformed_fts_syntax_is_never_forwarded() -> None:
    query = normalize_query('Pimba" OR * NEAR( outage')

    assert "*" not in query.fts_query
    assert "NEAR(" not in query.fts_query


def test_subject_match_can_rerank_lower_fts_candidate() -> None:
    query = normalize_query("Pimba outage")
    candidates = (
        RetrievalCandidate(
            _record("body", subject="Note", body="Pimba outage " * 4), -5.0, 1
        ),
        RetrievalCandidate(
            _record("subject", subject="Pimba outage", body="Update"), -4.0, 2
        ),
    )

    ranked = DeterministicReranker().rerank(query, candidates)

    assert ranked[0].candidate.record.source_record_key == "subject"
    assert "subject match 2" in ranked[0].explanations


def test_exact_phrase_preference_is_explainable(tmp_path: Path) -> None:
    engine = _engine(
        tmp_path,
        (
            _record(
                "separate", subject="Pimba note", body="A major outage affected Pimba."
            ),
            _record("phrase", subject="Report", body="The Pimba outage was resolved."),
        ),
    )

    evidence = engine.retrieve("Explain the Pimba outage", limit=2)

    assert evidence[0].source_record_key == "phrase"
    assert "exact phrase" in evidence[0].explanations


def test_ticket_identifier_is_detected_and_ranked() -> None:
    query = normalize_query("Status of INC-1042?")
    assert query.identifiers == ("INC-1042",)

    candidates = (
        RetrievalCandidate(
            _record("other", subject="INC update", body="INC status"), -2.0, 1
        ),
        RetrievalCandidate(
            _record("exact", subject="INC-1042", body="Resolved"), -1.0, 2
        ),
    )
    ranked = DeterministicReranker().rerank(query, candidates)
    assert ranked[0].candidate.record.source_record_key == "exact"
    assert "identifier match" in ranked[0].explanations


def test_hostname_identifier_is_detected_and_ranked() -> None:
    query = normalize_query("Tell me about edge-rtr-01")
    assert query.identifiers == ("edge-rtr-01",)

    candidates = (
        RetrievalCandidate(
            _record("general", subject="Edge router", body="Router 01"), -2.0, 1
        ),
        RetrievalCandidate(
            _record("host", subject="edge-rtr-01", body="Commissioned"), -1.0, 2
        ),
    )
    ranked = DeterministicReranker().rerank(query, candidates)
    assert ranked[0].candidate.record.source_record_key == "host"


def test_stable_order_uses_fts_rank_then_source_key() -> None:
    zero_weights = RerankWeights(
        keyword_rank=0,
        subject_match=0,
        sender_match=0,
        folder_match=0,
        body_term=0,
        body_term_cap=0,
        exact_phrase=0,
        acronym=0,
        identifier=0,
        recent=0,
    )
    candidates = (
        RetrievalCandidate(_record("b", subject="Pimba", body="Pimba"), -1.0, 2),
        RetrievalCandidate(_record("a", subject="Pimba", body="Pimba"), -1.0, 1),
    )

    ranked = DeterministicReranker(zero_weights).rerank(
        normalize_query("Pimba"), candidates
    )
    assert [item.candidate.record.source_record_key for item in ranked] == ["a", "b"]


def test_engine_returns_rich_evidence_and_bounds_candidates(tmp_path: Path) -> None:
    evidence = _engine(
        tmp_path,
        (_record("pimba", subject="Pimba outage", body="Service restored."),),
    ).retrieve("Pimba", limit=1)

    assert evidence[0].fts_rank == 1
    assert evidence[0].score > 0
    assert evidence[0].body_reference == "pimba"
    assert evidence[0].semantic_score is None
    assert evidence[0].explanations


def test_current_retrieval_regression_preserves_grounded_result(tmp_path: Path) -> None:
    engine = _engine(
        tmp_path,
        (_record("pimba", subject="Pimba restoration", body="Service restored."),),
    )

    assert engine.retrieve("What happened at Pimba?")[0].source_record_key == "pimba"
