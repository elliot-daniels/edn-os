"""Import email records from MBOX files."""

from __future__ import annotations

import hashlib
import json
import mailbox
from dataclasses import dataclass, replace
from email.message import Message
from pathlib import Path

from edn.memory.models import EmailRecord
from edn.memory.parser import parse_message
from edn.memory.storage import SQLiteEmailStore


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Summary of one MBOX import operation."""

    imported: int
    skipped: int


def _fallback_record_key(record: EmailRecord) -> str:
    """Create a stable content key when Message-ID is unavailable."""
    canonical = {
        "subject": record.subject,
        "sender": record.sender,
        "recipients_to": record.recipients_to,
        "recipients_cc": record.recipients_cc,
        "recipients_bcc": record.recipients_bcc,
        "sent_at": record.sent_at.isoformat() if record.sent_at else None,
        "body_text": record.body_text,
    }
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"content-sha256:{hashlib.sha256(payload).hexdigest()}"


def _source_record_key(record: EmailRecord) -> str:
    """Prefer Message-ID, falling back to a canonical content digest."""
    if record.message_id:
        message_id = record.message_id.strip()
        if message_id:
            return f"message-id:{message_id}"
    return _fallback_record_key(record)


def _parse_mbox_message(
    message: Message,
    *,
    folder_path: str,
) -> EmailRecord:
    """Parse one MBOX message and assign a stable source record key."""
    provisional = parse_message(
        message=message,
        source_record_key="pending",
        folder_path=folder_path,
    )
    return replace(
        provisional,
        source_record_key=_source_record_key(provisional),
    )


def import_mbox(
    mbox_path: str | Path,
    store: SQLiteEmailStore,
    *,
    folder_path: str = "Inbox",
) -> ImportResult:
    """Import all messages from an MBOX file into an email store."""
    path = Path(mbox_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    imported = 0
    skipped = 0
    source = mailbox.mbox(path, create=False)

    try:
        for message in source:
            record = _parse_mbox_message(
                message,
                folder_path=folder_path,
            )
            if store.add(record):
                imported += 1
            else:
                skipped += 1
    finally:
        source.close()

    return ImportResult(imported=imported, skipped=skipped)
