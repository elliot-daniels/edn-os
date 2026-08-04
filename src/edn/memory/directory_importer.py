"""Import all MBOX files beneath a directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from edn.memory.importer import import_mbox
from edn.memory.storage import SQLiteEmailStore


@dataclass(frozen=True, slots=True)
class DirectoryImportResult:
    """Summary of a recursive MBOX directory import."""

    files_processed: int
    imported: int
    skipped: int


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
) -> DirectoryImportResult:
    """Recursively import every MBOX file beneath a directory."""
    root_path = Path(root)
    mbox_files = find_mbox_files(root_path)

    imported = 0
    skipped = 0

    for mbox_path in mbox_files:
        result = import_mbox(
            mbox_path,
            store,
            folder_path=_folder_path(root_path, mbox_path),
        )
        imported += result.imported
        skipped += result.skipped

    return DirectoryImportResult(
        files_processed=len(mbox_files),
        imported=imported,
        skipped=skipped,
    )
