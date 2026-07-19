"""Command-line interface for EDN email memory."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from edn.memory.directory_importer import import_mbox_directory
from edn.memory.importer import import_mbox
from edn.memory.storage import SQLiteEmailStore


def _store(database: str | Path) -> SQLiteEmailStore:
    store = SQLiteEmailStore(database)
    store.initialise()
    return store


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edn-memory",
        description="Import and search EDN email memory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create or upgrade an email memory database.",
    )
    init_parser.add_argument("database", type=Path)

    import_parser = subparsers.add_parser(
        "import",
        help="Import an MBOX file into the database.",
    )
    import_parser.add_argument("database", type=Path)
    import_parser.add_argument("mbox", type=Path)
    import_parser.add_argument(
        "--folder",
        default="Inbox",
        help="Folder path stored against imported messages.",
    )

    import_directory_parser = subparsers.add_parser(
        "import-directory",
        help="Import every MBOX beneath a directory.",
    )
    import_directory_parser.add_argument("database", type=Path)
    import_directory_parser.add_argument("directory", type=Path)

    search_parser = subparsers.add_parser(
        "search",
        help="Search stored email subject, sender and body text.",
    )
    search_parser.add_argument("database", type=Path)
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Show database record totals.",
    )
    stats_parser.add_argument("database", type=Path)

    return parser


def _run_init(database: Path) -> int:
    _store(database)
    print(f"Initialised email memory database: {database}")
    return 0


def _run_import(database: Path, mbox_path: Path, folder_path: str) -> int:
    result = import_mbox(
        mbox_path,
        _store(database),
        folder_path=folder_path,
    )
    print(f"Imported: {result.imported}")
    print(f"Skipped: {result.skipped}")
    return 0



def _run_import_directory(
    database: Path,
    directory: Path,
) -> int:
    result = import_mbox_directory(
        directory,
        _store(database),
    )
    print(f"Files: {result.files_processed}")
    print(f"Imported: {result.imported}")
    print(f"Skipped: {result.skipped}")
    return 0

def _run_search(database: Path, query: str, limit: int) -> int:
    records = _store(database).search(query, limit=limit)
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
    total = _store(database).count()
    print(f"Emails: {total}")
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
        return _run_import_directory(
            args.database,
            args.directory,
        )
    if args.command == "search":
        return _run_search(args.database, args.query, args.limit)
    if args.command == "stats":
        return _run_stats(args.database)

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
