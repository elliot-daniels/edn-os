"""Tests for recursive MBOX directory imports."""

import mailbox
from email.message import EmailMessage
from pathlib import Path

import pytest

from edn.memory.directory_importer import (
    find_mbox_files,
    import_mbox_directory,
)
from edn.memory.storage import SQLiteEmailStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteEmailStore:
    """Return an initialised temporary email store."""
    email_store = SQLiteEmailStore(tmp_path / "memory.db")
    email_store.initialise()
    return email_store


def _write_mbox(
    path: Path,
    *,
    subject: str,
    message_id: str,
) -> None:
    """Create an MBOX file containing one test message."""
    path.parent.mkdir(parents=True, exist_ok=True)

    destination = mailbox.mbox(path)
    message = EmailMessage()
    message["From"] = "engineer@example.com"
    message["To"] = "elliot@ednsystems.com.au"
    message["Date"] = "Sat, 18 Jul 2026 10:30:00 +0000"
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message.set_content(f"Body for {subject}.")

    try:
        destination.add(message)
        destination.flush()
    finally:
        destination.close()


def test_find_mbox_files_is_recursive_and_sorted(tmp_path: Path) -> None:
    _write_mbox(
        tmp_path / "Sent.mbox",
        subject="Sent",
        message_id="<sent@example.com>",
    )
    _write_mbox(
        tmp_path / "Projects" / "Apex.mbox",
        subject="Apex",
        message_id="<apex@example.com>",
    )
    _write_mbox(
        tmp_path / "Inbox" / "mbox",
        subject="Inbox",
        message_id="<inbox@example.com>",
    )
    (tmp_path / "ignore.txt").write_text("not an mbox", encoding="utf-8")

    result = find_mbox_files(tmp_path)

    assert result == (
        tmp_path / "Inbox" / "mbox",
        tmp_path / "Projects" / "Apex.mbox",
        tmp_path / "Sent.mbox",
    )


def test_import_directory_preserves_folder_paths(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    export_root = tmp_path / "outlook-export"

    _write_mbox(
        export_root / "Inbox.mbox",
        subject="Inbox message",
        message_id="<inbox@example.com>",
    )
    _write_mbox(
        export_root / "Projects" / "Apex.mbox",
        subject="Apex message",
        message_id="<apex@example.com>",
    )

    result = import_mbox_directory(export_root, store)

    assert result.files_processed == 2
    assert result.imported == 2
    assert result.skipped == 0
    assert store.count() == 2

    inbox = store.get("message-id:<inbox@example.com>")
    apex = store.get("message-id:<apex@example.com>")

    assert inbox is not None
    assert apex is not None
    assert inbox.folder_path == "Inbox"
    assert apex.folder_path == "Projects/Apex"


def test_import_directory_supports_readpst_mbox_layout(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    export_root = tmp_path / "outlook-export"

    _write_mbox(
        export_root / "Inbox" / "CRQ" / "mbox",
        subject="CRQ message",
        message_id="<crq@example.com>",
    )

    result = import_mbox_directory(export_root, store)

    assert result.files_processed == 1
    assert result.imported == 1
    assert result.skipped == 0

    record = store.get("message-id:<crq@example.com>")

    assert record is not None
    assert record.folder_path == "Inbox/CRQ"


def test_reimport_directory_skips_existing_messages(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    export_root = tmp_path / "outlook-export"
    _write_mbox(
        export_root / "Inbox.mbox",
        subject="Duplicate test",
        message_id="<duplicate@example.com>",
    )

    first = import_mbox_directory(export_root, store)
    second = import_mbox_directory(export_root, store)

    assert first.imported == 1
    assert first.skipped == 0
    assert second.imported == 0
    assert second.skipped == 1
    assert store.count() == 1


def test_missing_directory_raises_not_a_directory(
    tmp_path: Path,
    store: SQLiteEmailStore,
) -> None:
    with pytest.raises(NotADirectoryError):
        import_mbox_directory(tmp_path / "missing", store)
