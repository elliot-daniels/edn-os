"""Tests for safe deterministic email evidence retrieval."""

from datetime import UTC, datetime
from pathlib import Path

from edn.knowledge.retrieval import (
    build_fts_query,
    question_to_search_terms,
    retrieve_email_evidence,
)
from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore


def _record(
    key: str,
    *,
    subject: str,
    body: str,
    sender: str = "engineer@example.com",
) -> EmailRecord:
    return EmailRecord(
        source_record_key=key,
        folder_path="Inbox/Incidents",
        subject=subject,
        sender=sender,
        recipients_to=("elliot@example.com",),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=datetime(2026, 7, 18, 10, 30, tzinfo=UTC),
        received_at=None,
        message_id=f"<{key}@example.com>",
        body_text=body,
    )


def _store(tmp_path: Path) -> SQLiteEmailStore:
    store = SQLiteEmailStore(tmp_path / "memory.db")
    store.initialise()
    return store


def test_question_to_search_terms_removes_noise_and_punctuation() -> None:
    assert question_to_search_terms(
        "What happened during the Pimba outage?! (MX304)"
    ) == ("pimba", "outage", "mx304")


def test_question_to_search_terms_is_unique_and_bounded() -> None:
    question = "one one two three four five six seven eight nine ten"

    assert question_to_search_terms(question) == (
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
    )


def test_build_fts_query_accepts_only_tokenized_terms() -> None:
    assert build_fts_query(("pimba", 'bad" OR *', "mx304")) == (
        '"pimba" OR "mx304"'
    )


def test_retrieve_email_evidence_preserves_relevance_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add(
        _record(
            "primary",
            subject="Pimba outage Pimba",
            body="Pimba outage investigation and restoration.",
        )
    )
    store.add(
        _record(
            "secondary",
            subject="Operations note",
            body="A later note mentioned Pimba once.",
        )
    )

    evidence = retrieve_email_evidence("What happened at Pimba?", store)

    assert [item.source_record_key for item in evidence] == [
        "primary",
        "secondary",
    ]
    assert [item.evidence_id for item in evidence] == [1, 2]


def test_retrieve_email_evidence_limits_and_centers_excerpt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    body = "prefix " * 30 + "Pimba restoration completed" + " suffix" * 30
    store.add(_record("long", subject="Incident", body=body))

    evidence = retrieve_email_evidence(
        "Pimba restoration",
        store,
        excerpt_characters=80,
    )

    assert len(evidence) == 1
    assert len(evidence[0].body_excerpt) <= 80
    assert "Pimba restoration" in evidence[0].body_excerpt
    assert evidence[0].body_text == body


def test_retrieve_email_evidence_handles_question_with_only_punctuation(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    assert retrieve_email_evidence("?! ---", store) == ()
