"""Tests for Memory domain models."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from edn.memory.models import EmailRecord


def test_email_record_preserves_parsed_email_data() -> None:
    """EmailRecord should retain canonical parsed email fields."""

    sent_at = datetime(2026, 7, 18, 10, 30, tzinfo=UTC)

    record = EmailRecord(
        source_record_key="sent-items:000001",
        folder_path="Sent Items",
        subject="Test subject",
        sender="elliot@example.com",
        recipients_to=("recipient@example.com",),
        recipients_cc=("copy@example.com",),
        recipients_bcc=(),
        sent_at=sent_at,
        received_at=None,
        message_id="<test-message@example.com>",
        body_text="This is the plain-text body.",
    )

    assert record.subject == "Test subject"
    assert record.sender == "elliot@example.com"
    assert record.recipients_to == ("recipient@example.com",)
    assert record.sent_at == sent_at
    assert record.folder_path == "Sent Items"


def test_email_record_is_immutable() -> None:
    """Canonical records should not be modified after parsing."""

    record = EmailRecord(
        source_record_key="sent-items:000001",
        folder_path="Sent Items",
        subject="Original subject",
        sender="elliot@example.com",
        recipients_to=(),
        recipients_cc=(),
        recipients_bcc=(),
        sent_at=None,
        received_at=None,
        message_id=None,
        body_text="Body",
    )

    with pytest.raises(FrozenInstanceError):
        record.subject = "Changed subject"  # type: ignore[misc]
