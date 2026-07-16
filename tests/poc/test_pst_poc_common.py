"""Tests for shared PST PoC utilities (synthetic data only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from poc.pst.common import (
    ProbeReport,
    ensure_output_directory,
    inspect_pst_access,
    measure_elapsed,
    probe_report_to_dict,
    sqlite_fts5_available,
    write_json_report,
)


def test_inspect_pst_access_missing_path(tmp_path: Path) -> None:
    report = inspect_pst_access(tmp_path / "missing.pst")

    assert report.exists is False
    assert report.readable is False


def test_inspect_pst_access_readable_file(tmp_path: Path) -> None:
    pst_file = tmp_path / "sample.pst"
    pst_file.write_bytes(b"fake-pst-header")

    report = inspect_pst_access(pst_file)

    assert report.exists is True
    assert report.is_file is True
    assert report.readable is True
    assert report.size_bytes == len(b"fake-pst-header")


def test_ensure_output_directory_rejects_beside_pst(tmp_path: Path) -> None:
    pst_file = tmp_path / "source" / "archive.pst"
    pst_file.parent.mkdir(parents=True)
    pst_file.write_bytes(b"x")
    output_dir = pst_file.parent / "reports"

    with pytest.raises(ValueError, match="must not be inside"):
        ensure_output_directory(output_dir, pst_file)


def test_ensure_output_directory_allows_separate_location(tmp_path: Path) -> None:
    pst_file = tmp_path / "source" / "archive.pst"
    pst_file.parent.mkdir(parents=True)
    pst_file.write_bytes(b"x")
    output_dir = tmp_path / "reports"

    created = ensure_output_directory(output_dir, pst_file)

    assert created.is_dir()


def test_write_json_report_roundtrip(tmp_path: Path) -> None:
    payload = {"status": "completed", "count": 3}
    target = write_json_report(tmp_path, "report.json", payload)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == payload


def test_probe_report_to_dict() -> None:
    report = ProbeReport(
        probe="test",
        status="completed",
        started_at="2026-01-01T00:00:00+00:00",
        elapsed_seconds=1.5,
    )
    data = probe_report_to_dict(report)

    assert data["probe"] == "test"
    assert data["elapsed_seconds"] == 1.5


def test_measure_elapsed_records_time() -> None:
    with measure_elapsed() as elapsed:
        total = sum(range(1000))
    assert elapsed[0] > 0.0
    assert total == 499_500


def test_sqlite_fts5_available() -> None:
    result = sqlite_fts5_available()
    assert result["available"] is True
