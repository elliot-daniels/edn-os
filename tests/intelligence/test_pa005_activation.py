from pathlib import Path

import pytest

from edn.intelligence.pa005_activation import _preflight, _validate_output


def test_preflight_is_fixed_and_has_no_source_activity(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    report = _preflight(output)

    assert report["delegated_permissions"] == ["Calendars.Read", "Mail.Read"]
    assert report["network_calls"] == 0
    assert report["source_reads"] == 0
    assert report["calendar"] == {
        "id": "default",
        "window": "this-week",
        "limit": 25,
    }
    assert report["mail"] == {
        "folder": "inbox",
        "window": "last-7-days",
        "limit": 25,
    }


def test_output_is_no_clobber(tmp_path: Path) -> None:
    output = tmp_path / "existing.json"
    output.write_text("protected", encoding="utf-8")

    with pytest.raises(ValueError, match="no-clobber"):
        _validate_output(output)
