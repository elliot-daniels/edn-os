"""Import email records from MBOX files."""

from __future__ import annotations

import hashlib
import json
import mailbox
from collections.abc import Callable
from dataclasses import dataclass, replace
from email.message import Message
from pathlib import Path
from typing import Literal

from edn.memory.models import EmailRecord
from edn.memory.parser import parse_message
from edn.memory.storage import SQLiteEmailStore

DEFAULT_IMPORT_BATCH_SIZE = 250
ProgressStatus = Literal["running", "completed", "failed", "interrupted"]


@dataclass(frozen=True, slots=True)
class ImportProgress:
    """Body-free progress data emitted only at transaction boundaries."""

    folder_path: str
    processed: int
    imported: int
    skipped: int
    batches_committed: int
    status: ProgressStatus


ProgressCallback = Callable[[ImportProgress], None]


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Summary of one MBOX import operation."""

    imported: int
    skipped: int
    processed: int
    batches_committed: int


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
    batch_size: int = DEFAULT_IMPORT_BATCH_SIZE,
    progress: ProgressCallback | None = None,
) -> ImportResult:
    """Import an MBOX in duplicate-safe, resumable transaction batches."""
    path = Path(mbox_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    imported = 0
    skipped = 0
    processed = 0
    batches_committed = 0
    pending: list[EmailRecord] = []
    source = mailbox.mbox(path, create=False)

    def emit(status: ProgressStatus) -> None:
        if progress is not None:
            progress(
                ImportProgress(
                    folder_path=folder_path,
                    processed=processed,
                    imported=imported,
                    skipped=skipped,
                    batches_committed=batches_committed,
                    status=status,
                )
            )

    def commit_pending() -> None:
        nonlocal imported, skipped, batches_committed
        if not pending:
            return
        batch_result = store.add_many(pending)
        imported += batch_result.imported
        skipped += batch_result.skipped
        batches_committed += 1
        pending.clear()
        emit("running")

    try:
        for message in source:
            pending.append(
                _parse_mbox_message(
                    message,
                    folder_path=folder_path,
                )
            )
            processed += 1
            if len(pending) >= batch_size:
                commit_pending()
        commit_pending()
    except KeyboardInterrupt:
        emit("interrupted")
        raise
    except Exception:
        emit("failed")
        raise
    finally:
        source.close()

    emit("completed")
    return ImportResult(
        imported=imported,
        skipped=skipped,
        processed=processed,
        batches_committed=batches_committed,
    )
