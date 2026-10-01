"""Domain models owned by the EDN OS Memory module."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EmailRecord:
    """Canonical representation of an email imported into Memory."""

    source_record_key: str
    folder_path: str
    subject: str
    sender: str
    recipients_to: tuple[str, ...]
    recipients_cc: tuple[str, ...]
    recipients_bcc: tuple[str, ...]
    sent_at: datetime | None
    received_at: datetime | None
    message_id: str | None
    body_text: str
