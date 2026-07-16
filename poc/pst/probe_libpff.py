"""Probe PST access via libpff/pypff without exporting bodies or attachments."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from poc.pst.common import (
    ProbeReport,
    ensure_output_directory,
    inspect_pst_access,
    measure_elapsed,
    probe_report_to_dict,
    try_import_pypff,
    utc_now_iso,
    write_json_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a PST using pypff/libpff.")
    parser.add_argument("--pst", type=Path, required=True, help="Path to the PST file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for JSON output (must not be beside the PST).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Maximum number of message-like items to inspect for metadata.",
    )
    return parser.parse_args(argv)


def probe_with_pypff(pst_path: Path, sample_size: int) -> dict[str, Any]:
    import pypff

    pff_file = pypff.file()
    pff_file.open(str(pst_path))

    folder_paths: list[str] = []
    message_count = 0
    samples: list[dict[str, Any]] = []
    unicode_observations: list[str] = []
    nested_folder_count = 0

    def walk_folder(folder: Any, prefix: str) -> None:
        nonlocal message_count, nested_folder_count
        name = _safe_name(folder.get_name())
        current = f"{prefix}/{name}" if prefix else name
        folder_paths.append(current)
        if prefix:
            nested_folder_count += 1

        for message in _iter_messages(folder):
            message_count += 1
            if len(samples) < sample_size:
                samples.append(_inspect_message_metadata(message, current))

        for subfolder in _iter_subfolders(folder):
            walk_folder(subfolder, current)

    try:
        root = pff_file.get_root_folder()
        walk_folder(root, "")
    finally:
        pff_file.close()

    for sample in samples:
        for key, value in sample.items():
            if isinstance(value, str) and any(ord(char) > 127 for char in value):
                unicode_observations.append(f"Non-ASCII in sample field {key!r}.")

    return {
        "folder_count": len(folder_paths),
        "folder_paths_sample": folder_paths[:20],
        "nested_folder_count": nested_folder_count,
        "message_like_count": message_count,
        "metadata_samples": samples,
        "metadata_fields_observed": sorted(
            {field for sample in samples for field in sample}
        ),
        "unicode_observations": unicode_observations,
    }


def _iter_subfolders(folder: Any) -> list[Any]:
    subfolders: list[Any] = []
    count = folder.get_number_of_sub_folders()
    for index in range(count):
        subfolders.append(folder.get_sub_folder(index))
    return subfolders


def _iter_messages(folder: Any) -> list[Any]:
    messages: list[Any] = []
    count = folder.get_number_of_sub_messages()
    for index in range(count):
        messages.append(folder.get_sub_message(index))
    return messages


def _inspect_message_metadata(message: Any, folder_path: str) -> dict[str, Any]:
    record: dict[str, Any] = {"folder_path": folder_path}
    for getter, field_name in (
        ("get_subject", "subject"),
        ("get_sender_name", "sender_name"),
        ("get_sender_email_address", "sender_email"),
        ("get_delivery_time", "delivery_time"),
        ("get_client_submit_time", "client_submit_time"),
        ("get_conversation_topic", "conversation_topic"),
        ("get_transport_headers", "transport_headers_present"),
    ):
        if hasattr(message, getter):
            value = getattr(message, getter)()
            if field_name == "transport_headers_present":
                record[field_name] = bool(value)
            else:
                record[field_name] = _safe_value(value)
    record["plain_text_body_available"] = hasattr(message, "get_plain_text_body")
    record["html_body_available"] = hasattr(message, "get_html_body")
    record["attachment_count"] = _safe_attachment_count(message)
    return record


def _safe_attachment_count(message: Any) -> int | None:
    if not hasattr(message, "get_number_of_attachments"):
        return None
    try:
        return int(message.get_number_of_attachments())
    except (AttributeError, TypeError, ValueError):
        return None


def _safe_name(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = utc_now_iso()
    pst_access = inspect_pst_access(args.pst)
    availability = try_import_pypff()
    errors: list[str] = []
    details: dict[str, Any] = {"pst_access": pst_access.__dict__, "pypff": availability}
    status = "completed"
    elapsed_seconds = 0.0

    output_dir = ensure_output_directory(args.output_dir, args.pst)

    if not pst_access.readable:
        status = "failed"
        errors.append(pst_access.error or "PST is not readable.")
    elif not availability.get("available"):
        status = "unavailable"
        errors.append(str(availability.get("error", "pypff is not importable.")))
    else:
        with measure_elapsed() as elapsed:
            try:
                details["probe"] = probe_with_pypff(args.pst, args.sample_size)
            except Exception as exc:
                status = "failed"
                errors.append(str(exc))
        elapsed_seconds = elapsed[0]

    report = ProbeReport(
        probe="probe_libpff",
        status=status,
        started_at=started_at,
        elapsed_seconds=elapsed_seconds,
        pst_path=str(args.pst),
        output_dir=str(output_dir),
        details=details,
        errors=errors,
    )
    target = write_json_report(
        output_dir, "probe_libpff.json", probe_report_to_dict(report)
    )
    print(f"Status: {status}")
    print(f"Wrote {target}")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
