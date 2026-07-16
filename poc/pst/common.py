"""Shared utilities for the PST extractor proof of concept.

Disposable evaluation code — not imported by the production ``edn`` package.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POC_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class PstAccessReport:
    """Read-only access facts for a PST path."""

    path: str
    exists: bool
    is_file: bool
    size_bytes: int | None
    readable: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """Standard envelope for PoC probe JSON output."""

    probe: str
    status: str
    started_at: str
    elapsed_seconds: float
    pst_path: str | None = None
    output_dir: str | None = None
    python_version: str = field(default_factory=lambda: sys.version)
    platform: str = field(default_factory=lambda: platform.platform())
    details: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@contextmanager
def measure_elapsed() -> Iterator[list[float]]:
    """Yield a single-element list populated with elapsed seconds on exit."""
    container: list[float] = [0.0]
    start = time.perf_counter()
    try:
        yield container
    finally:
        container[0] = time.perf_counter() - start


def ensure_output_directory(output_dir: Path, pst_path: Path | None = None) -> Path:
    """Create ``output_dir`` if needed and ensure it is not beside the PST."""
    resolved_output = output_dir.resolve()
    if pst_path is not None:
        pst_resolved = pst_path.resolve()
        pst_parent = pst_resolved.parent
        if resolved_output == pst_parent or pst_parent in resolved_output.parents:
            msg = (
                "Output directory must not be inside or equal to the PST source "
                f"directory ({pst_parent})."
            )
            raise ValueError(msg)
        if pst_resolved in resolved_output.parents or resolved_output == pst_resolved:
            msg = "Output directory must not contain the PST file path."
            raise ValueError(msg)
    resolved_output.mkdir(parents=True, exist_ok=True)
    return resolved_output


def write_json_report(output_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    """Write a UTF-8 JSON report and return the file path."""
    target = output_dir / filename
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return target


def probe_report_to_dict(report: ProbeReport) -> dict[str, Any]:
    return asdict(report)


def inspect_pst_access(pst_path: Path) -> PstAccessReport:
    """Report existence, size and read access without reading message content."""
    path_str = str(pst_path)
    if not pst_path.exists():
        return PstAccessReport(
            path=path_str,
            exists=False,
            is_file=False,
            size_bytes=None,
            readable=False,
            error="Path does not exist.",
        )
    if not pst_path.is_file():
        return PstAccessReport(
            path=path_str,
            exists=True,
            is_file=False,
            size_bytes=None,
            readable=False,
            error="Path is not a regular file.",
        )
    size_bytes = pst_path.stat().st_size
    readable = os.access(pst_path, os.R_OK)
    error = None if readable else "File is not readable."
    return PstAccessReport(
        path=path_str,
        exists=True,
        is_file=True,
        size_bytes=size_bytes,
        readable=readable,
        error=error,
    )


def free_disk_bytes(path: Path) -> int | None:
    """Return free bytes for the volume containing ``path``."""
    try:
        target = path if path.exists() else path.parent
        usage = shutil.disk_usage(target.resolve())
    except OSError:
        return None
    return usage.free


def command_on_path(name: str) -> str | None:
    return shutil.which(name)


def try_import_pypff() -> dict[str, Any]:
    """Attempt to import pypff without installing anything."""
    try:
        import pypff
    except ImportError as exc:
        return {
            "available": False,
            "error": str(exc),
            "notes": (
                "pypff requires libpff bindings built for the current Python "
                "version. On Windows this often needs manual build tooling."
            ),
        }
    version = getattr(pypff, "__version__", None)
    return {"available": True, "module": "pypff", "version": version}


def sqlite_fts5_available() -> dict[str, Any]:
    """Check whether the running SQLite build supports FTS5."""
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE t USING fts5(content)")
        connection.close()
    except sqlite3.OperationalError as exc:
        return {"available": False, "error": str(exc)}
    return {"available": True}


def detect_wsl() -> dict[str, Any]:
    """Detect WSL presence without modifying the system."""
    wsl_path = command_on_path("wsl")
    if wsl_path is None:
        return {"installed": False, "executable": None}
    try:
        import subprocess

        completed = subprocess.run(
            ["wsl", "--status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return {
            "installed": True,
            "executable": wsl_path,
            "status_returncode": completed.returncode,
            "status_stdout": completed.stdout.strip() or None,
            "status_stderr": completed.stderr.strip() or None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "installed": True,
            "executable": wsl_path,
            "status_error": str(exc),
        }


def detect_cygwin() -> dict[str, Any]:
    """Detect common Cygwin installation markers."""
    markers = [
        Path(r"C:\cygwin64"),
        Path(r"C:\cygwin"),
    ]
    found = [str(path) for path in markers if path.exists()]
    env_cygwin = os.environ.get("CYGWIN")
    return {
        "detected": bool(found or env_cygwin),
        "paths": found,
        "CYGWIN_env": env_cygwin,
    }


def fingerprint_pst_if_requested(pst_path: Path, requested: bool) -> str | None:
    """Return SHA-256 only when explicitly requested."""
    if not requested:
        return None
    from edn.foundation.fingerprint import sha256_file

    return sha256_file(pst_path)
