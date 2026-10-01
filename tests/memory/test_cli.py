"""Tests for the EDN email-memory command-line interface."""

import mailbox
from email.message import EmailMessage
from pathlib import Path

import pytest

from edn.memory.cli import main


def _write_mbox(path: Path) -> None:
    destination = mailbox.mbox(path)
    message = EmailMessage()
    message["From"] = "engineer@example.com"
    message["To"] = "elliot@ednsystems.com.au"
    message["Date"] = "Sat, 18 Jul 2026 10:30:00 +0000"
    message["Subject"] = "Juniper commissioning"
    message["Message-ID"] = "<cli-one@example.com>"
    message.set_content("MX304 commissioning completed.")
    try:
        destination.add(message)
        destination.flush()
    finally:
        destination.close()


def test_init_creates_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "memory.db"

    result = main(["init", str(database)])

    assert result == 0
    assert database.is_file()
    captured = capsys.readouterr()
    assert "Initialised email memory database" in captured.out


def test_import_and_stats_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "inbox.mbox"
    _write_mbox(mbox_path)

    import_result = main(
        [
            "import",
            str(database),
            str(mbox_path),
            "--folder",
            "Projects/Inbox",
        ]
    )
    import_output = capsys.readouterr().out

    stats_result = main(["stats", str(database)])
    stats_output = capsys.readouterr().out

    assert import_result == 0
    assert "Imported: 1" in import_output
    assert "Skipped: 0" in import_output
    assert stats_result == 0
    assert "Emails: 1" in stats_output


def test_search_prints_matching_email(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "memory.db"
    mbox_path = tmp_path / "inbox.mbox"
    _write_mbox(mbox_path)
    main(["import", str(database), str(mbox_path)])
    capsys.readouterr()

    result = main(["search", str(database), "MX304"])
    output = capsys.readouterr().out

    assert result == 0
    assert "Juniper commissioning" in output
    assert "engineer@example.com" in output
    assert "message-id:<cli-one@example.com>" in output


def test_search_prints_no_matches(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "memory.db"
    main(["init", str(database)])
    capsys.readouterr()

    result = main(["search", str(database), "nonexistent"])
    output = capsys.readouterr().out

    assert result == 0
    assert output == "No matching emails.\n"
