"""Import all MBOX files beneath a directory."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from edn.memory.importer import ImportProgress, ProgressCallback, import_mbox
from edn.memory.storage import SQLiteEmailStore


@dataclass(frozen=True, slots=True)
class MailboxImportSummary:
    """Body-free statistics for one attempted mailbox."""

    folder_path: str
    imported: int
    skipped: int
    processed: int
    batches_committed: int
    elapsed_seconds: float
    error: str | None = None


@dataclass(frozen=True, slots=True)
class DirectoryImportResult:
    """Summary of a recursive MBOX directory import."""

    files_processed: int
    imported: int
    skipped: int
    failed_files: int
    mailboxes: tuple[MailboxImportSummary, ...]


def _folder_path(root: Path, mbox_path: Path) -> str:
    """Derive the stored mailbox folder path from an MBOX file path."""
    relative_path = mbox_path.relative_to(root)
    if relative_path.name.lower() == "mbox":
        return relative_path.parent.as_posix()
    return relative_path.with_suffix("").as_posix()


def find_mbox_files(root: str | Path) -> tuple[Path, ...]:
    """Return all MBOX files beneath a directory in deterministic order."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)
    return tuple(
        sorted(
            path
            for path in root_path.rglob("*")
            if path.is_file()
            and (
                path.suffix.lower() == ".mbox"
                or path.name.lower() == "mbox"
            )
        )
    )


def import_mbox_directory(
    root: str | Path,
    store: SQLiteEmailStore,
    *,
    progress: ProgressCallback | None = None,
) -> DirectoryImportResult:
    """Recursively import mailboxes and report each failure without data loss."""
    root_path = Path(root)
    mbox_files = find_mbox_files(root_path)
    imported = 0
    skipped = 0
    failed_files = 0
    mailbox_summaries: list[MailboxImportSummary] = []

    for mbox_path in mbox_files:
        folder_path = _folder_path(root_path, mbox_path)
        started_at = time.monotonic()
        latest_progress: ImportProgress | None = None

        def track_progress(event: ImportProgress) -> None:
            nonlocal latest_progress
            latest_progress = event
            if progress is not None:
                progress(event)

        try:
            result = import_mbox(
                mbox_path,
                store,
                folder_path=folder_path,
                progress=track_progress,
            )
        except Exception as error:
            failed_files += 1
            committed = latest_progress
            if committed is not None:
                imported += committed.imported
                skipped += committed.skipped
            mailbox_summaries.append(
                MailboxImportSummary(
                    folder_path=folder_path,
                    imported=0 if committed is None else committed.imported,
                    skipped=0 if committed is None else committed.skipped,
                    processed=0 if committed is None else committed.processed,
                    batches_committed=(
                        0 if committed is None else committed.batches_committed
                    ),
                    elapsed_seconds=time.monotonic() - started_at,
                    error=f"{type(error).__name__}: {error}",
                )
            )
            continue
        imported += result.imported
        skipped += result.skipped
        mailbox_summaries.append(
            MailboxImportSummary(
                folder_path=folder_path,
                imported=result.imported,
                skipped=result.skipped,
                processed=result.processed,
                batches_committed=result.batches_committed,
                elapsed_seconds=time.monotonic() - started_at,
            )
        )

    return DirectoryImportResult(
        files_processed=len(mbox_files),
        imported=imported,
        skipped=skipped,
        failed_files=failed_files,
        mailboxes=tuple(mailbox_summaries),
    )
