"""Testable application services for the local email-search interface."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from edn.memory.models import EmailRecord
from edn.memory.storage import SQLiteEmailStore

DATABASE_ENVIRONMENT_VARIABLE = "EDN_MEMORY_DB"
DEFAULT_RESULT_LIMIT = 20
MAX_RESULT_LIMIT = 100
DEFAULT_PREVIEW_LENGTH = 240


class DatabaseConfigurationError(ValueError):
    """Raised when the email-memory database cannot be configured safely."""


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured database cannot be read."""


class SearchQueryError(ValueError):
    """Raised when SQLite FTS5 cannot understand a search query."""


@dataclass(frozen=True, slots=True)
class EmailResultView:
    """Presentation-safe fields for one email search result."""

    subject: str
    sender: str
    sent_date: str
    folder_path: str
    provenance_key: str
    body_preview: str
    body_text: str


def resolve_database_path(
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the required database path without using an unsafe default."""
    values = os.environ if environment is None else environment
    configured_path = values.get(DATABASE_ENVIRONMENT_VARIABLE, "").strip()
    if not configured_path:
        raise DatabaseConfigurationError(
            f"Set {DATABASE_ENVIRONMENT_VARIABLE} to an existing EDN memory database."
        )
    return Path(configured_path).expanduser()


def open_read_only_store(database_path: Path) -> SQLiteEmailStore:
    """Open an existing initialized email store in SQLite read-only mode."""
    if not database_path.is_file():
        raise DatabaseUnavailableError(
            "The configured EDN memory database does not exist or is not a file."
        )

    store = SQLiteEmailStore(database_path, read_only=True)
    try:
        store.count()
    except sqlite3.Error as error:
        raise DatabaseUnavailableError(
            "The configured file is not a readable initialized EDN memory database."
        ) from error
    return store


def search_emails(
    store: SQLiteEmailStore,
    query: str,
    *,
    limit: int = DEFAULT_RESULT_LIMIT,
) -> list[EmailRecord]:
    """Search email memory and translate SQLite query errors for the UI."""
    normalized_query = query.strip()
    if not normalized_query:
        return []
    if not 1 <= limit <= MAX_RESULT_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RESULT_LIMIT}")

    try:
        return store.search(normalized_query, limit=limit)
    except sqlite3.OperationalError as error:
        raise SearchQueryError(
            "That search could not be understood. "
            "Try plain keywords or a quoted phrase."
        ) from error


def body_preview(
    body_text: str,
    *,
    max_characters: int = DEFAULT_PREVIEW_LENGTH,
) -> str:
    """Return a compact plain-text preview without loading additional records."""
    if max_characters < 2:
        raise ValueError("max_characters must be at least 2")

    normalized = " ".join(body_text.split())
    if not normalized:
        return "(No plain-text body)"
    if len(normalized) <= max_characters:
        return normalized
    return normalized[: max_characters - 1].rstrip() + "…"


def format_sent_date(value: datetime | None) -> str:
    """Format a stored timestamp for compact local display."""
    if value is None:
        return "Unknown date"
    return value.astimezone().strftime("%d %b %Y, %I:%M %p %Z")


def format_result(record: EmailRecord) -> EmailResultView:
    """Build display fields while preserving the record's provenance key."""
    return EmailResultView(
        subject=record.subject or "(No subject)",
        sender=record.sender or "(Unknown sender)",
        sent_date=format_sent_date(record.sent_at),
        folder_path=record.folder_path or "(Unknown folder)",
        provenance_key=record.message_id or record.source_record_key,
        body_preview=body_preview(record.body_text),
        body_text=record.body_text or "(No plain-text body)",
    )
