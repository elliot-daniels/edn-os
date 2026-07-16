"""Probe PST access via readpst without retaining converted message content."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from poc.pst.common import (
    ProbeReport,
    command_on_path,
    ensure_output_directory,
    inspect_pst_access,
    measure_elapsed,
    probe_report_to_dict,
    utc_now_iso,
    write_json_report,
)

READPST_INSTALL_OPTIONS = [
    "Cygwin: install the libpst/readpst package inside Cygwin.",
    "WSL: install readpst via the Linux distribution package manager.",
    "MSYS2/MinGW: build or install libpst providing readpst on PATH.",
    "Manual: build libpst from source and add readpst to PATH.",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a PST using readpst.")
    parser.add_argument("--pst", type=Path, required=True, help="Path to the PST file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for JSON output (must not be beside the PST).",
    )
    parser.add_argument(
        "--allow-conversion-sample",
        action="store_true",
        help="If listing is unsupported, run the smallest conversion sample.",
    )
    return parser.parse_args(argv)


def readpst_version(executable: str) -> dict[str, Any]:
    completed = subprocess.run(
        [executable, "-V"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip() or None,
        "stderr": completed.stderr.strip() or None,
    }


def run_readpst_listing(executable: str, pst_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [executable, "-l", "-r", str(pst_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "mode": "list_only",
        "returncode": completed.returncode,
        "stdout_line_count": len(lines),
        "stdout_sample": lines[:20],
        "stderr": completed.stderr.strip() or None,
    }


def run_readpst_conversion_sample(
    executable: str,
    pst_path: Path,
    temp_output: Path,
) -> dict[str, Any]:
    if any(temp_output.iterdir()):
        msg = f"Refusing to overwrite existing output in {temp_output}."
        raise ValueError(msg)

    completed = subprocess.run(
        [executable, "-r", "-o", str(temp_output), str(pst_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    created = [str(path.relative_to(temp_output)) for path in temp_output.rglob("*")]
    return {
        "mode": "conversion_sample",
        "returncode": completed.returncode,
        "created_entry_count": len(created),
        "created_entries_sample": created[:20],
        "stderr": completed.stderr.strip() or None,
        "retained_output": False,
        "note": "Temporary conversion output deleted after inspection.",
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = utc_now_iso()
    pst_access = inspect_pst_access(args.pst)
    readpst_executable = command_on_path("readpst")
    errors: list[str] = []
    details: dict[str, Any] = {
        "pst_access": pst_access.__dict__,
        "readpst_executable": readpst_executable,
        "installation_options": READPST_INSTALL_OPTIONS,
    }
    status = "completed"
    elapsed_seconds = 0.0

    output_dir = ensure_output_directory(args.output_dir, args.pst)

    if not pst_access.readable:
        status = "failed"
        errors.append(pst_access.error or "PST is not readable.")
    elif readpst_executable is None:
        status = "unavailable"
        errors.append("readpst is not available on PATH.")
    else:
        with measure_elapsed() as elapsed:
            details["version"] = readpst_version(readpst_executable)
            listing = run_readpst_listing(readpst_executable, args.pst)
            details["listing"] = listing
            if listing["returncode"] != 0 and args.allow_conversion_sample:
                with tempfile.TemporaryDirectory(prefix="edn-readpst-") as temp_name:
                    temp_output = Path(temp_name)
                    details["conversion_sample"] = run_readpst_conversion_sample(
                        readpst_executable,
                        args.pst,
                        temp_output,
                    )
            elif listing["returncode"] != 0:
                status = "failed"
                errors.append("readpst listing failed; conversion sample not approved.")
        elapsed_seconds = elapsed[0]

    report = ProbeReport(
        probe="probe_readpst",
        status=status,
        started_at=started_at,
        elapsed_seconds=elapsed_seconds,
        pst_path=str(args.pst),
        output_dir=str(output_dir),
        details=details,
        errors=errors,
    )
    target = write_json_report(
        output_dir, "probe_readpst.json", probe_report_to_dict(report)
    )
    print(f"Status: {status}")
    print(f"Wrote {target}")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
