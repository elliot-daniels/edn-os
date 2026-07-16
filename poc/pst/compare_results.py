"""Compare JSON reports from PST extractor probes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare probe_libpff and probe_readpst JSON reports.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        required=True,
        help="Directory containing probe JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for comparison JSON output.",
    )
    return parser.parse_args(argv)


def load_report(path: Path) -> dict[str, Any]:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"Expected JSON object in {path}"
        raise ValueError(msg)
    return data


def build_comparison(
    libpff_report: dict[str, Any] | None,
    readpst_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "winner": None,
        "note": "No adapter selected until operator reviews real probe results.",
        "libpff": _summarise_probe(libpff_report),
        "readpst": _summarise_probe(readpst_report),
        "comparison_fields": [
            "status",
            "elapsed_seconds",
            "message_like_count_or_listing_lines",
            "metadata_fields_observed",
            "errors",
        ],
    }


def _summarise_probe(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"present": False}
    details = report.get("details", {})
    probe_details = details.get("probe") or details.get("listing") or {}
    return {
        "present": True,
        "status": report.get("status"),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "errors": report.get("errors", []),
        "message_like_count": probe_details.get("message_like_count"),
        "listing_line_count": probe_details.get("stdout_line_count"),
        "metadata_fields_observed": probe_details.get("metadata_fields_observed"),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    libpff_path = args.reports_dir / "probe_libpff.json"
    readpst_path = args.reports_dir / "probe_readpst.json"

    comparison = build_comparison(
        load_report(libpff_path) if libpff_path.is_file() else None,
        load_report(readpst_path) if readpst_path.is_file() else None,
    )

    text = json.dumps(comparison, indent=2, sort_keys=True)
    print(text)

    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
