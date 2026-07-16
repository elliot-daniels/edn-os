"""Report local environment facts for PST extractor evaluation.

Does not modify the system, inspect email content, or write under E:\\EDN OS
unless the operator explicitly supplies an output path there.
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from poc.pst.common import (
    ProbeReport,
    command_on_path,
    detect_cygwin,
    detect_wsl,
    ensure_output_directory,
    fingerprint_pst_if_requested,
    free_disk_bytes,
    inspect_pst_access,
    measure_elapsed,
    probe_report_to_dict,
    sqlite_fts5_available,
    try_import_pypff,
    utc_now_iso,
    write_json_report,
)


def build_environment_report(
    pst_path: Path | None,
    output_drive: Path | None,
    fingerprint_requested: bool,
) -> dict[str, object]:
    pst_report = inspect_pst_access(pst_path) if pst_path is not None else None
    fingerprint = None
    if (
        pst_path is not None
        and fingerprint_requested
        and pst_report
        and pst_report.readable
    ):
        fingerprint = fingerprint_pst_if_requested(pst_path, True)

    disk_target = output_drive or (pst_path.parent if pst_path else Path.cwd())
    free_bytes = free_disk_bytes(disk_target)

    return {
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "wsl": detect_wsl(),
        "cygwin": detect_cygwin(),
        "readpst_on_path": command_on_path("readpst"),
        "pypff": try_import_pypff(),
        "sqlite_fts5": sqlite_fts5_available(),
        "disk": {
            "target": str(disk_target),
            "free_bytes": free_bytes,
        },
        "pst": None
        if pst_report is None
        else {
            **pst_report.__dict__,
            "fingerprint_sha256": fingerprint,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the local environment for PST extractor PoC work.",
    )
    parser.add_argument(
        "--pst",
        type=Path,
        help="Optional PST path to check for existence, size and read access.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for the JSON report. Required to write output.",
    )
    parser.add_argument(
        "--output-drive",
        type=Path,
        help="Drive or directory for free-space reporting (defaults near PST or cwd).",
    )
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        help="Compute SHA-256 for the PST when --pst is supplied.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = utc_now_iso()

    with measure_elapsed() as elapsed:
        details = build_environment_report(
            pst_path=args.pst,
            output_drive=args.output_drive,
            fingerprint_requested=args.fingerprint,
        )
    elapsed_seconds = elapsed[0]

    report = ProbeReport(
        probe="inspect_environment",
        status="completed",
        started_at=started_at,
        elapsed_seconds=elapsed_seconds,
        pst_path=str(args.pst) if args.pst else None,
        output_dir=str(args.output_dir) if args.output_dir else None,
        details=details,
    )

    print(build_text_summary(details))

    if args.output_dir is None:
        print("No --output-dir supplied; JSON report not written.")
        return 0

    output_dir = ensure_output_directory(args.output_dir, args.pst)

    target = write_json_report(
        output_dir,
        "environment.json",
        probe_report_to_dict(report),
    )
    print(f"Wrote {target}")
    return 0


def build_text_summary(details: dict[str, object]) -> str:
    python_info = details["python"]
    assert isinstance(python_info, dict)
    lines = [
        "EDN OS PST PoC — environment inspection",
        f"OS: {details['operating_system']}",
        f"Architecture: {details['architecture']}",
        f"Python: {python_info['version'].split()[0]} ({python_info['executable']})",
        f"readpst on PATH: {details['readpst_on_path']}",
        f"pypff available: {details['pypff']}",
        f"SQLite FTS5: {details['sqlite_fts5']}",
    ]
    pst = details.get("pst")
    if isinstance(pst, dict):
        lines.append(
            f"PST: exists={pst['exists']} readable={pst['readable']} "
            f"size_bytes={pst['size_bytes']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
