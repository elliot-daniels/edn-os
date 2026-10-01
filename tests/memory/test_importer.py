"""Tests for importing MBOX files into email storage."""

import mailbox
from email.message import EmailMessage
from pathlib import Path

import pytest

from edn.memory.importer import import_mbox
from edn.memory.storage import SQLiteEmailStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteEmailStore:
    """Return an initialised temporary email store."""
    email_store = SQLiteEmailStore(tmp_path / "memory.db")
    email_store.initialise()
    return email_store


def _write_mbox(path: Path, messages: list[EmailMessage]) -> None:
    """Create an MBOX file containing the supplied messages."""
    destination = mailbox.mbox(path)
    try:
        for message in messages:
            destination.add(message)
        destination.flush()
    finally:
        destination.close()


def _message(
    *,
    subject: str,
    body: str,
    message_id: str | None = None,
) -> EmailMessage:
    """Build a simple test email."""
    message = EmailMessage()
    message["From"] = "engineer@example.com"
    message["To"] = "elliot@ednsystems.com.au"
    message["Date"] = "Sat, 18 Jul 2026 10:30:00 +0000"
    message["Subject"] = subject
    if message_id is not None:
        message["Message-ID"] = message_id
    message.set_content(body)
    return message


def test_import_mbox_stores_messages(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    mbox_path = tmp_path / "inbox.mbox"
    _write_mbox(
        mbox_path,
        [
            _message(
                subject="Juniper commissioning",
                body="Commissioning completed.",
                message_id="<one@example.com>",
            ),
            _message(
                subject="Apex invoice",
                body="Please approve the invoice.",
                message_id="<two@example.com>",
            ),
        ],
    )

    result = import_mbox(
        mbox_path,
        store,
        folder_path="Projects/Inbox",
    )

    assert result.imported == 2
    assert result.skipped == 0
    assert store.count() == 2
    stored = store.get("message-id:<one@example.com>")
    assert stored is not None
    assert stored.folder_path == "Projects/Inbox"


def test_reimport_skips_duplicate_message_ids(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    mbox_path = tmp_path / "inbox.mbox"
    _write_mbox(
        mbox_path,
        [
            _message(
                subject="Juniper commissioning",
                body="Commissioning completed.",
                message_id="<one@example.com>",
            )
        ],
    )

    first = import_mbox(mbox_path, store)
    second = import_mbox(mbox_path, store)

    assert first.imported == 1
    assert first.skipped == 0
    assert second.imported == 0
    assert second.skipped == 1
    assert store.count() == 1


def test_missing_message_id_uses_stable_content_hash(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    first_path = tmp_path / "first.mbox"
    second_path = tmp_path / "second.mbox"
    email = _message(
        subject="No identifier",
        body="This message has no Message-ID.",
    )
    _write_mbox(first_path, [email])
    _write_mbox(second_path, [email])

    first = import_mbox(first_path, store)
    second = import_mbox(second_path, store)

    assert first.imported == 1
    assert second.skipped == 1
    assert store.count() == 1


def test_missing_mbox_raises_file_not_found(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    with pytest.raises(FileNotFoundError):
        import_mbox(tmp_path / "missing.mbox", store)
