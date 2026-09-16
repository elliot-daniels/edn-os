"""Backward-compatible email schema and persisted import lifecycle coverage."""

import mailbox
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from edn.memory.importer import import_mbox
from edn.memory.storage import SQLiteEmailStore
from tests.intelligence.test_recent_email_brief import _record

NOW = datetime(2026, 9, 16, tzinfo=UTC)


def test_legacy_read_remains_read_only_and_explicit_initialise_adds_index(tmp_path):
    path = tmp_path / "legacy.db"
    store = SQLiteEmailStore(path)
    store.initialise()
    store.add_many((_record("recent", NOW),))
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TABLE email_import_status")
        connection.execute("DROP INDEX emails_sent_instant")
        connection.commit()
    before = path.read_bytes()
    readonly = SQLiteEmailStore(path, read_only=True)
    assert readonly.import_status() == ()
    assert len(readonly.recent(since=NOW - timedelta(days=1), until=NOW)) == 1
    assert path.read_bytes() == before
    store.initialise()
    store.initialise()
    assert store.count() == 1
    with closing(sqlite3.connect(path)) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM emails WHERE julianday(sent_at) "
            "BETWEEN julianday(?) AND julianday(?) "
            "ORDER BY julianday(sent_at) DESC, source_record_key LIMIT 10",
            ((NOW - timedelta(days=1)).isoformat(), NOW.isoformat()),
        ).fetchall()
    assert "emails_sent_instant" in str(plan)


def test_import_records_terminal_metadata_without_persisting_path_or_content(tmp_path):
    path = tmp_path / "synthetic.mbox"
    source = mailbox.mbox(path)
    message = EmailMessage()
    message["Subject"] = "Synthetic-only import"
    message["From"] = "synthetic@example.test"
    message["Date"] = "Wed, 16 Sep 2026 00:00:00 +0000"
    message.set_content("Synthetic content")
    source.add(message)
    source.close()
    store = SQLiteEmailStore(tmp_path / "mail.db")
    store.initialise()
    import_mbox(path, store)
    assert {status for status, _ in store.import_status()} == {"completed"}
    with closing(sqlite3.connect(tmp_path / "mail.db")) as connection:
        rows = connection.execute("SELECT * FROM email_import_status").fetchall()
    assert str(path) not in str(rows)
    assert "Synthetic content" not in str(rows)


def test_import_metadata_retains_oldest_and_future_completed_snapshot(tmp_path):
    store = SQLiteEmailStore(tmp_path / "mail.db")
    store.initialise()
    store.record_import_status("old", "completed", NOW - timedelta(days=4))
    store.record_import_status("future", "completed", NOW + timedelta(days=1))
    assert {at for _, at in store.import_status()} == {
        NOW - timedelta(days=4),
        NOW + timedelta(days=1),
    }
