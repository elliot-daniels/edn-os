"""Read-only business Inbox ingestion with explicit account scope and provenance."""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from edn.connectors.microsoft_outlook.client import (
    MicrosoftGraphOutlookClient,
    TokenProvider,
)
from edn.operations.import_outcomes import ImportOutcomeStore
from edn.operations.models import Event, validate_attachments
from edn.operations.storage import EventStore

MAX_PAGE_RECORDS = 50


def validate_window(start: datetime, end: datetime) -> None:
    if (
        start.utcoffset() is None
        or end.utcoffset() is None
        or end < start
        or end - start > timedelta(days=31)
    ):
        raise ValueError("Mail window must be aware, ordered and at most 31 days")


class OperationsOutlookClient(MicrosoftGraphOutlookClient):
    """Separate content-read path; legacy PA-005 methods retain their bounds."""

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        mailboxes: tuple[str, ...],
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if not mailboxes or any(
            "@" not in value or value != value.strip() for value in mailboxes
        ):
            raise ValueError("Explicit business mailbox email addresses are required")
        self.mailboxes = tuple(value.casefold() for value in mailboxes)
        options = {} if opener is None else {"opener": opener}
        super().__init__(
            token_provider,
            prefer='IdType="ImmutableId", outlook.body-content-type="text"',
            **options,
        )

    def page(
        self,
        mailbox: str,
        start: datetime,
        end: datetime,
        *,
        continuation: str | None = None,
    ) -> dict[str, Any]:
        account = mailbox.casefold()
        if account not in self.mailboxes:
            raise ValueError("Mailbox is outside Operations read scope")
        validate_window(start, end)
        prefix = (
            f"{self._BASE}/users/{urllib.parse.quote(account, safe='')}/"
            "mailFolders/inbox/messages"
        )
        query = urllib.parse.urlencode(
            {
                "$select": "id,internetMessageId,parentFolderId,subject,body,from,"
                "toRecipients,ccRecipients,receivedDateTime,webLink,flag,hasAttachments",
                "$expand": "attachments($select=id,name,contentType,size,isInline)",
                "$filter": f"receivedDateTime ge {start.astimezone(UTC).isoformat()} "
                f"and receivedDateTime le {end.astimezone(UTC).isoformat()}",
                "$orderby": "receivedDateTime desc",
                "$top": str(MAX_PAGE_RECORDS),
            }
        )
        url = continuation or f"{prefix}?{query}"
        # Never forward a token to another host, mailbox or Graph resource.
        parsed = urllib.parse.urlsplit(url)
        expected = urllib.parse.urlsplit(prefix)
        if (parsed.scheme, parsed.netloc, parsed.path) != (
            expected.scheme,
            expected.netloc,
            expected.path,
        ) or parsed.fragment:
            raise ValueError("Unsafe Graph continuation")
        return self._get(url)


def mail_event(mailbox: str, payload: dict[str, Any]) -> Event:
    identifier = payload.get("id")
    timestamp = payload.get("receivedDateTime")
    if not isinstance(identifier, str) or not isinstance(timestamp, str):
        raise ValueError("Mail must carry native identity and received timestamp")
    body = payload.get("body", {})
    if (
        not isinstance(body, dict)
        or body.get("contentType", "text").casefold() != "text"
    ):
        raise ValueError("Operations mail requires a plain-text body")
    attachments = payload.get("attachments", [])
    validate_attachments(attachments)
    parties = []
    for role, recipients in (
        ("from", [payload.get("from", {})]),
        ("to", payload.get("toRecipients", [])),
        ("cc", payload.get("ccRecipients", [])),
    ):
        for recipient in recipients:
            address = recipient.get("emailAddress", {})
            if address.get("address"):
                parties.append({"role": role, **address})
    return Event(
        source="outlook",
        source_account=mailbox.casefold(),
        external_id=identifier,
        occurred_at=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        direction="inbound",
        event_type="email",
        parties=tuple(parties),
        subject=str(payload.get("subject", "")),
        body=str(body.get("content", "")),
        attachments=tuple(attachments),
        needs_action=payload.get("flag", {}).get("flagStatus") == "flagged",
        raw_payload=payload,
    )


@dataclass(frozen=True)
class IngestionReport:
    inserted: int
    duplicates: int
    failed: int
    complete: bool


def ingest_mailbox(
    client: OperationsOutlookClient,
    store: EventStore,
    mailbox: str,
    start: datetime,
    end: datetime,
    *,
    max_pages: int = 100,
    outcomes: ImportOutcomeStore | None = None,
) -> IngestionReport:
    validate_window(start, end)
    if not 1 <= max_pages <= 100:
        raise ValueError("Page limit must be between 1 and 100")
    if outcomes is None:
        return _ingest_mailbox(client, store, mailbox, start, end, max_pages=max_pages)
    run_id = outcomes.begin(mailbox, start, end)
    counts = [0, 0, 0, 0]

    def progress(inserted: int, duplicates: int, failed: int, pages: int) -> None:
        counts[:] = [inserted, duplicates, failed, pages]
        outcomes.update(
            run_id, inserted=inserted, duplicates=duplicates, failed=failed, pages=pages
        )

    try:
        report = _ingest_mailbox(
            client, store, mailbox, start, end, max_pages=max_pages, progress=progress
        )
    except Exception:
        outcomes.update(
            run_id,
            inserted=counts[0],
            duplicates=counts[1],
            failed=counts[2],
            pages=counts[3],
            state="partial" if any(counts) else "failed",
            reason="import_error",
        )
        raise
    outcomes.update(
        run_id,
        inserted=report.inserted,
        duplicates=report.duplicates,
        failed=report.failed,
        pages=counts[3],
        state="complete" if report.complete else "partial",
        reason=None
        if report.complete
        else "malformed_records"
        if report.failed
        else "page_limit",
    )
    return report


def _ingest_mailbox(
    client: OperationsOutlookClient,
    store: EventStore,
    mailbox: str,
    start: datetime,
    end: datetime,
    *,
    max_pages: int,
    progress: Callable[[int, int, int, int], None] | None = None,
) -> IngestionReport:
    if not 1 <= max_pages <= 100:
        raise ValueError("Page limit must be between 1 and 100")
    inserted = duplicates = failed = 0
    continuation = None
    visited: set[str] = set()
    for page_number in range(max_pages):
        page = client.page(mailbox, start, end, continuation=continuation)
        values = page.get("value")
        if not isinstance(values, list):
            raise ValueError("Graph mail page has no message collection")
        if len(values) > MAX_PAGE_RECORDS:
            raise ValueError("Graph mail page exceeds record limit")
        for payload in values:
            try:
                if not isinstance(payload, dict):
                    raise ValueError("Invalid mail record")
                record = mail_event(mailbox, payload)
                if not start <= record.occurred_at <= end:
                    raise ValueError("Mail is outside the requested window")
            except (ValueError, TypeError, AttributeError):
                failed += 1
                if progress is not None:
                    progress(inserted, duplicates, failed, page_number)
                continue
            result = store.insert(record)
            inserted += int(result.inserted)
            duplicates += int(not result.inserted)
            if progress is not None:
                progress(inserted, duplicates, failed, page_number)
        if progress is not None:
            progress(inserted, duplicates, failed, page_number + 1)
        continuation = page.get("@odata.nextLink")
        if continuation is None:
            return IngestionReport(inserted, duplicates, failed, failed == 0)
        if not isinstance(continuation, str) or continuation in visited:
            raise ValueError("Invalid or repeated Graph continuation")
        visited.add(continuation)
    return IngestionReport(inserted, duplicates, failed, False)
