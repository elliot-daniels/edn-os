"""Parser for canonical email records."""

from __future__ import annotations

from datetime import datetime
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from edn.memory.models import EmailRecord


def _addresses(value: str | None) -> tuple[str, ...]:
    """Return email addresses from an address header."""
    if not value:
        return ()
    return tuple(address for _, address in getaddresses([value]) if address)


def _parse_date(value: str | None) -> datetime | None:
    """Parse an RFC email date, returning None when absent or invalid."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _decode_payload(part: Message) -> str:
    """Decode a non-multipart message payload as text."""
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    if isinstance(payload, str):
        return payload
    return ""


def _body(message: Message) -> str:
    """Extract the first non-attachment plain-text body."""
    if not message.is_multipart():
        return _decode_payload(message)

    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/plain":
            return _decode_payload(part)
    return ""


def parse_message(
    *,
    message: Message,
    source_record_key: str,
    folder_path: str,
) -> EmailRecord:
    """Convert one parsed email message into an EmailRecord."""
    sender = (
        message.get("X-libpst-forensic-sender")
        or message.get("From")
        or ""
    )

    return EmailRecord(
        source_record_key=source_record_key,
        folder_path=folder_path,
        subject=message.get("Subject", ""),
        sender=sender,
        recipients_to=_addresses(message.get("To")),
        recipients_cc=_addresses(message.get("Cc")),
        recipients_bcc=_addresses(message.get("Bcc")),
        sent_at=_parse_date(message.get("Date")),
        received_at=None,
        message_id=message.get("Message-ID"),
        body_text=_body(message),
    )
