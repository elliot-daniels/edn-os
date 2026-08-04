"""Synthetic production-hardening tests for SQLite email import."""

from __future__ import annotations

import mailbox
import sqlite3
import threading
import time
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest

from edn.memory.importer import ImportProgress, import_mbox
from edn.memory.models import EmailRecord
from edn.memory.storage import (
    BatchAddResult,
    DatabaseBusyError,
    SQLiteEmailStore,
    retry_on_database_busy,
)
from edn.ui.service import (
    DatabaseTemporarilyBusyError,
    search_emails,
)


def _record(index: int) -> EmailRecord:
    return EmailRecord(
        source_record_key=f"message-{index}",
        folder_path="Inbox/Test",
        subject=f"Synthetic message {index}",
        sender="engineer@example.com",
        recipients_to=("elliot@example.com",),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=datetime(2026, 8, 4, 10, index % 60, tzinfo=UTC),
        received_at=None,
        message_id=f"<message-{index}@example.com>",
        body_text=f"Synthetic body {index}",
    )


def _write_mbox(path: Path, count: int) -> None:
    destination = mailbox.mbox(path)
    try:
        for index in range(count):
            message = EmailMessage()
            message["From"] = "engineer@example.com"
            message["To"] = "elliot@example.com"
            message["Date"] = "Tue, 04 Aug 2026 10:30:00 +0000"
            message["Subject"] = f"Synthetic message {index}"
            message["Message-ID"] = f"<message-{index}@example.com>"
            message.set_content(f"Synthetic body {index}")
            destination.add(message)
        destination.flush()
    finally:
        destination.close()


def _store(path: Path, **kwargs: object) -> SQLiteEmailStore:
    store = SQLiteEmailStore(path, **kwargs)
    store.initialise()
    return store


def test_retry_after_transient_lock_uses_exponential_backoff() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        return "complete"

    result = retry_on_database_busy(
        operation,
        max_retries=3,
        base_delay_seconds=0.25,
        sleep=delays.append,
    )

    assert result == "complete"
    assert attempts == 3
    assert delays == [0.25, 0.5]


def test_retry_exhaustion_raises_friendly_busy_error() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("database is busy")

    with pytest.raises(DatabaseBusyError, match="bounded retries"):
        retry_on_database_busy(
            operation,
            max_retries=2,
            base_delay_seconds=0,
        )

    assert attempts == 3


def test_batch_commits_use_one_connection_per_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "mailbox.mbox"
    store = _store(database)
    _write_mbox(mbox_path, 5)
    real_connect = sqlite3.connect
    connection_count = 0

    def counting_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal connection_count
        connection_count += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", counting_connect)

    result = import_mbox(mbox_path, store, batch_size=2)

    assert result.batches_committed == 3
    assert connection_count == 3
    assert result.imported == 5


def test_interrupted_import_keeps_committed_batches_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "mailbox.mbox"
    store = _store(database)
    _write_mbox(mbox_path, 5)
    real_add_many = store.add_many
    calls = 0

    def interrupting_add_many(
        records: tuple[EmailRecord, ...] | list[EmailRecord],
    ) -> BatchAddResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return real_add_many(records)

    monkeypatch.setattr(store, "add_many", interrupting_add_many)

    with pytest.raises(KeyboardInterrupt):
        import_mbox(mbox_path, store, batch_size=2)

    assert store.count() == 2
    monkeypatch.setattr(store, "add_many", real_add_many)
    resumed = import_mbox(mbox_path, store, batch_size=2)
    assert resumed.imported == 3
    assert resumed.skipped == 2
    assert store.count() == 5


def test_reimport_is_duplicate_safe_for_batches(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "mailbox.mbox"
    store = _store(database)
    _write_mbox(mbox_path, 4)

    first = import_mbox(mbox_path, store, batch_size=3)
    second = import_mbox(mbox_path, store, batch_size=3)

    assert first.imported == 4
    assert second.imported == 0
    assert second.skipped == 4
    assert store.count() == 4


def test_progress_reports_committed_batches_and_completion(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "mailbox.mbox"
    store = _store(database)
    _write_mbox(mbox_path, 3)
    events: list[ImportProgress] = []

    result = import_mbox(
        mbox_path,
        store,
        folder_path="Inbox/Test",
        batch_size=2,
        progress=events.append,
    )

    assert result.batches_committed == 2
    assert [event.status for event in events] == [
        "running",
        "running",
        "completed",
    ]
    assert events[-1].processed == 3
    assert events[-1].imported == 3
    assert all("Synthetic body" not in repr(event) for event in events)


def test_read_only_store_rejects_batch_writes(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    _store(database)
    read_store = SQLiteEmailStore(database, read_only=True)

    with pytest.raises(sqlite3.OperationalError, match="read-only"):
        read_store.add_many((_record(1),))

    assert read_store.count() == 0


def test_concurrent_reader_and_writer_complete_in_rollback_mode(
    tmp_path: Path,
) -> None:
    database = tmp_path / "memory.db"
    writer = _store(
        database,
        connection_timeout_seconds=1,
        busy_timeout_ms=1_000,
        max_lock_retries=2,
        retry_base_delay_seconds=0.01,
    )
    reader_connection = sqlite3.connect(database)
    reader_connection.execute("BEGIN")
    reader_connection.execute("SELECT COUNT(*) FROM emails").fetchone()
    outcome: list[BatchAddResult] = []

    thread = threading.Thread(
        target=lambda: outcome.append(writer.add_many((_record(1),))),
        daemon=True,
    )
    thread.start()
    time.sleep(0.05)
    reader_connection.commit()
    reader_connection.close()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert outcome == [BatchAddResult(imported=1, skipped=0)]
    assert SQLiteEmailStore(database, read_only=True).count() == 1


class _BusySearchStore:
    def search(self, query: str, *, limit: int = 20) -> list[EmailRecord]:
        del query, limit
        raise DatabaseBusyError("database is locked")


def test_ui_translates_busy_database_without_stack_trace() -> None:
    store = _BusySearchStore()

    with pytest.raises(DatabaseTemporarilyBusyError, match="temporarily busy"):
        search_emails(store, "Pimba")  # type: ignore[arg-type]
