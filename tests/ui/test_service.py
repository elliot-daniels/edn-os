"""Tests for non-visual local email-search behavior."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore
from edn.ui.service import (
    DatabaseConfigurationError,
    DatabaseUnavailableError,
    SearchQueryError,
    body_preview,
    format_result,
    open_read_only_store,
    resolve_database_path,
    search_emails,
)


def _record(*, body_text: str = "Juniper outage resolved.") -> EmailRecord:
    return EmailRecord(
        source_record_key="message-id:<result@example.com>",
        folder_path="Inbox/Support",
        subject="Juniper incident",
        sender="engineer@example.com",
        recipients_to=("elliot@example.com",),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=datetime(2026, 7, 18, 10, 30, tzinfo=UTC),
        received_at=None,
        message_id="<result@example.com>",
        body_text=body_text,
    )


def _initialized_database(path: Path) -> SQLiteEmailStore:
    store = SQLiteEmailStore(path)
    store.initialise()
    return store


def test_resolve_database_path_uses_environment_value(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"

    assert resolve_database_path({"EDN_MEMORY_DB": str(database)}) == database


def test_resolve_database_path_requires_configuration() -> None:
    with pytest.raises(DatabaseConfigurationError, match="EDN_MEMORY_DB"):
        resolve_database_path({})


def test_open_read_only_store_rejects_missing_database(tmp_path: Path) -> None:
    database = tmp_path / "missing.db"

    with pytest.raises(DatabaseUnavailableError, match="does not exist"):
        open_read_only_store(database)

    assert not database.exists()


def test_open_read_only_store_rejects_uninitialized_file(tmp_path: Path) -> None:
    database = tmp_path / "not-a-database.db"
    database.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(DatabaseUnavailableError, match="not a readable"):
        open_read_only_store(database)


def test_read_only_store_searches_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    writable_store = _initialized_database(database)
    writable_store.add(_record())

    read_only_store = open_read_only_store(database)

    assert read_only_store.count() == 1
    assert search_emails(read_only_store, "Juniper") == [_record()]


def test_read_only_store_rejects_initialization(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    _initialized_database(database)
    store = open_read_only_store(database)

    with pytest.raises(sqlite3.OperationalError, match="read-only"):
        store.initialise()


def test_search_emails_ignores_blank_query(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    store = _initialized_database(database)

    assert search_emails(store, "   ") == []


def test_search_emails_rejects_malformed_fts_query(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    store = _initialized_database(database)
    store.add(_record())

    with pytest.raises(SearchQueryError, match="could not be understood"):
        search_emails(store, '"unterminated')


def test_search_emails_validates_limit(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    store = _initialized_database(database)

    with pytest.raises(ValueError, match="between 1 and 100"):
        search_emails(store, "Juniper", limit=101)


def test_body_preview_normalizes_and_truncates_plain_text() -> None:
    body = " First line.\n\nSecond   line. "

    assert body_preview(body) == "First line. Second line."
    assert body_preview(body, max_characters=15) == "First line. Se…"
    assert body_preview("   ") == "(No plain-text body)"


def test_format_result_preserves_readable_metadata() -> None:
    result = format_result(_record())

    assert result.subject == "Juniper incident"
    assert result.sender == "engineer@example.com"
    assert result.sent_date.startswith("18 Jul 2026")
    assert result.folder_path == "Inbox/Support"
    assert result.provenance_key == "<result@example.com>"
    assert result.body_preview == "Juniper outage resolved."
    assert result.body_text == "Juniper outage resolved."
