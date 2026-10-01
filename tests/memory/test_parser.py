"""Tests for the Memory email parser."""

from datetime import UTC, datetime
from email.message import EmailMessage

from edn.memory.parser import parse_message


def test_parse_basic_email() -> None:
    """A simple email should become a canonical EmailRecord."""
    message = EmailMessage()
    message["Subject"] = "Parser Test"
    message["From"] = "elliot@example.com"
    message["To"] = "Recipient <recipient@example.com>"
    message["Cc"] = "copy@example.com"
    message["Date"] = "Sat, 18 Jul 2026 10:30:00 +0000"
    message["Message-ID"] = "<abc123@example.com>"
    message.set_content("Hello EDN OS")

    record = parse_message(
        message=message,
        source_record_key="test:000001",
        folder_path="Inbox",
    )

    assert record.subject == "Parser Test"
    assert record.sender == "elliot@example.com"
    assert record.recipients_to == ("recipient@example.com",)
    assert record.recipients_cc == ("copy@example.com",)
    assert record.sent_at == datetime(2026, 7, 18, 10, 30, tzinfo=UTC)
    assert record.folder_path == "Inbox"
    assert record.message_id == "<abc123@example.com>"
    assert record.body_text.strip() == "Hello EDN OS"


def test_forensic_sender_takes_priority_over_mailer_daemon() -> None:
    """readpst forensic sender data should be retained when present."""
    message = EmailMessage()
    message["From"] = "Elliot Daniels <MAILER-DAEMON>"
    message["X-libpst-forensic-sender"] = (
        "/o=ExchangeLabs/ou=Exchange Administrative Group/"
        "cn=Recipients/cn=elliot"
    )
    message.set_content("Body")

    record = parse_message(
        message=message,
        source_record_key="test:000002",
        folder_path="Sent Items",
    )

    assert record.sender.startswith("/o=ExchangeLabs/")


def test_multipart_email_uses_plain_text_and_skips_attachment() -> None:
    """The parser should select the plain-text body from multipart email."""
    message = EmailMessage()
    message["From"] = "elliot@example.com"
    message.set_content("Plain body")
    message.add_alternative("<p>HTML body</p>", subtype="html")
    message.add_attachment(
        b"attachment contents",
        maintype="application",
        subtype="octet-stream",
        filename="test.bin",
    )

    record = parse_message(
        message=message,
        source_record_key="test:000003",
        folder_path="Inbox",
    )

    assert record.body_text.strip() == "Plain body"


def test_invalid_date_does_not_abort_parsing() -> None:
    """Malformed source dates should become None rather than fail import."""
    message = EmailMessage()
    message["Date"] = "not a valid date"
    message.set_content("Body")

    record = parse_message(
        message=message,
        source_record_key="test:000004",
        folder_path="Inbox",
    )

    assert record.sent_at is None
