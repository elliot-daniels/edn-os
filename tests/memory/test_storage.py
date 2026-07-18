"""Tests for SQLite email persistence."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteEmailStore:
    email_store = SQLiteEmailStore(tmp_path / "memory.db")
    email_store.initialise()
    return email_store

def _record(
    *,
    key: str = "mbox:000001",
    subject: str = "Juniper MX304 commissioning",
    body: str = "Configuration and optical testing completed successfully.",
) -> EmailRecord:
    return EmailRecord(
        source_record_key=key,
        folder_path="Inbox/Projects",
        subject=subject,
        sender="engineer@example.com",
        recipients_to=("elliot@ednsystems.com.au",),
        recipients_cc=("operations@example.com",),
        recipients_bcc=(),
        sent_at=datetime(2026, 7, 18, 10, 30, tzinfo=UTC),
        received_at=datetime(2026, 7, 18, 10, 31, tzinfo=UTC),
        message_id="<message-1@example.com>",
        body_text=body,
    )

def test_add_and_get_round_trip(store: SQLiteEmailStore) -> None:
    original = _record()
    assert store.add(original) is True
    assert store.get(original.source_record_key) == original
    assert store.count() == 1

def test_duplicate_source_key_is_ignored(store: SQLiteEmailStore) -> None:
    record = _record()
    assert store.add(record) is True
    assert store.add(record) is False
    assert store.count() == 1

def test_get_missing_record_returns_none(store: SQLiteEmailStore) -> None:
    assert store.get("missing") is None

def test_search_finds_subject_and_body_terms(store: SQLiteEmailStore) -> None:
    store.add(_record())
    store.add(
        _record(
            key="mbox:000002",
            subject="Invoice approval",
            body="Approve the Apex invoice.",
        )
    )
    assert [r.source_record_key for r in store.search("Juniper")] == ["mbox:000001"]
    assert [r.source_record_key for r in store.search("Apex")] == ["mbox:000002"]

def test_search_rejects_invalid_limit(store: SQLiteEmailStore) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        store.search("Juniper", limit=0)
