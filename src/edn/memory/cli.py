"""Command-line interface for EDN email memory."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from edn.memory.directory_importer import import_mbox_directory
from edn.memory.importer import ImportProgress, import_mbox
from edn.memory.storage import DatabaseBusyError, SQLiteEmailStore


def _write_store(database: str | Path) -> SQLiteEmailStore:
    store = SQLiteEmailStore(database)
    store.initialise()
    return store


def _read_store(database: str | Path) -> SQLiteEmailStore:
    return SQLiteEmailStore(database, read_only=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edn-memory",
        description="Import and search EDN email memory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser(
        "init", help="Create or upgrade an email memory database."
    )
    init_parser.add_argument("database", type=Path)
    import_parser = subparsers.add_parser(
        "import", help="Import an MBOX file into the database."
    )
    import_parser.add_argument("database", type=Path)
    import_parser.add_argument("mbox", type=Path)
    import_parser.add_argument(
        "--folder",
        default="Inbox",
        help="Folder path stored against imported messages.",
    )
    import_directory_parser = subparsers.add_parser(
        "import-directory", help="Import every MBOX beneath a directory."
    )
    import_directory_parser.add_argument("database", type=Path)
    import_directory_parser.add_argument("directory", type=Path)
    search_parser = subparsers.add_parser(
        "search", help="Search stored email subject, sender and body text."
    )
    search_parser.add_argument("database", type=Path)
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)
    stats_parser = subparsers.add_parser(
        "stats", help="Show database record totals."
    )
    stats_parser.add_argument("database", type=Path)
    return parser


def _print_progress(progress: ImportProgress) -> None:
    print(
        f"Progress: {progress.folder_path} | Status: {progress.status} | "
        f"Processed: {progress.processed} | Imported: {progress.imported} | "
        f"Skipped: {progress.skipped} | Batches: {progress.batches_committed}",
        flush=True,
    )


def _run_init(database: Path) -> int:
    _write_store(database)
    print(f"Initialised email memory database: {database}")
    return 0


def _run_import(database: Path, mbox_path: Path, folder_path: str) -> int:
    try:
        result = import_mbox(
            mbox_path,
            _write_store(database),
            folder_path=folder_path,
            progress=_print_progress,
        )
    except KeyboardInterrupt:
        print(
            "Import interrupted. Committed batches are safe; rerun to resume.",
            file=sys.stderr,
        )
        return 130
    except DatabaseBusyError:
        print(
            "Import paused because the database remained busy. Rerun to resume.",
            file=sys.stderr,
        )
        return 1
    print(f"Imported: {result.imported}")
    print(f"Skipped: {result.skipped}")
    print(f"Processed: {result.processed}")
    print(f"Batches: {result.batches_committed}")
    return 0


def _run_import_directory(database: Path, directory: Path) -> int:
    try:
        result = import_mbox_directory(
            directory,
            _write_store(database),
            progress=_print_progress,
        )
    except KeyboardInterrupt:
        print(
            "Import interrupted. Committed batches are safe; rerun to resume.",
            file=sys.stderr,
        )
        return 130
    for mailbox in result.mailboxes:
        status = "failed" if mailbox.error else "completed"
        print(
            f"Mailbox: {mailbox.folder_path} | Status: {status} | "
            f"Processed: {mailbox.processed} | Imported: {mailbox.imported} | "
            f"Skipped: {mailbox.skipped} | Batches: {mailbox.batches_committed} | "
            f"Elapsed: {mailbox.elapsed_seconds:.2f}s"
        )
        if mailbox.error:
            print(f"  Error: {mailbox.error}")
    print(f"Files: {result.files_processed}")
    print(f"Imported: {result.imported}")
    print(f"Skipped: {result.skipped}")
    print(f"Failed: {result.failed_files}")
    return 1 if result.failed_files else 0


def _run_search(database: Path, query: str, limit: int) -> int:
    try:
        records = _read_store(database).search(query, limit=limit)
    except DatabaseBusyError:
        print(
            "The local email database is temporarily busy. Try again shortly.",
            file=sys.stderr,
        )
        return 1
    if not records:
        print("No matching emails.")
        return 0
    for record in records:
        sent_at = record.sent_at.isoformat() if record.sent_at else "unknown date"
        print(record.subject or "(no subject)")
        print(f"  From: {record.sender or '(unknown sender)'}")
        print(f"  Date: {sent_at}")
        print(f"  Folder: {record.folder_path}")
        print(f"  Key: {record.source_record_key}")
    return 0


def _run_stats(database: Path) -> int:
    try:
        store = _read_store(database)
        total = store.count()
        folder_counts = store.folder_counts()
    except DatabaseBusyError:
        print(
            "The local email database is temporarily busy. Try again shortly.",
            file=sys.stderr,
        )
        return 1
    print(f"Emails: {total}")
    for folder_path, folder_total in folder_counts:
        print(f"Folder: {folder_path} | Emails: {folder_total}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the EDN email-memory command-line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "init":
        return _run_init(args.database)
    if args.command == "import":
        return _run_import(args.database, args.mbox, args.folder)
    if args.command == "import-directory":
        return _run_import_directory(args.database, args.directory)
    if args.command == "search":
        return _run_search(args.database, args.query, args.limit)
    if args.command == "stats":
        return _run_stats(args.database)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
