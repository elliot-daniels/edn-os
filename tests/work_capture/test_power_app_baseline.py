from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "config" / "work-capture-power-app-baseline.json"
SOURCE = ROOT / "power-platform" / "work-capture" / "canvas" / "EDNWorkCapture" / "Src"


def _manifest() -> dict[str, object]:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_baseline_binds_the_exact_unshared_test_app() -> None:
    value = _manifest()
    app = value["app"]
    safety = value["safety"]
    assert isinstance(app, dict)
    assert isinstance(safety, dict)

    assert app["display_name"] == "EDN Work Capture"
    assert app["app_id"] == "a47efc3e-0b52-405a-a220-54930a4ffdc9"
    assert app["environment_id"] == "Default-aae6ab79-45eb-4829-a04f-595becdb936d"
    assert app["shared_users"] == 0
    assert app["shared_groups"] == 0
    assert safety["external_mutations"] == 0
    assert safety["sharepoint_item_reads"] == 0
    assert safety["customer_data_used"] is False


def test_only_supported_generated_canvas_source_is_retained() -> None:
    value = _manifest()
    source_control = value["source_control"]
    assert isinstance(source_control, dict)
    hashes = source_control["files"]
    assert isinstance(hashes, dict)

    assert {path.name for path in SOURCE.iterdir()} == set(hashes)
    for name, expected_hash in hashes.items():
        path = SOURCE / str(name)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_hash


def test_source_preserves_canonical_bindings_and_exposes_scaffold_gaps() -> None:
    source = (SOURCE / "Screen1.pa.yaml").read_text(encoding="utf-8")

    assert "DataSource: ='Work Log'" in source
    assert "DefaultMode: =FormMode.New" in source
    assert 'DataField: ="ProjectLookup"' in source
    assert 'DataField: ="ClientLookup"' in source
    assert 'DataField: ="TechnicalSummary"' in source
    assert "Default: =Today()" in source
    assert source.count('Text: ="30m"') == 4
    assert "SubmitForm(" not in source
    assert "OutcomeStatus" not in source


def test_deprecated_round_trip_and_live_update_remain_blocked() -> None:
    value = _manifest()
    export = value["export"]
    live_update = value["live_update"]
    assert isinstance(export, dict)
    assert isinstance(live_update, dict)

    assert export["deprecated_pack_unpack_used"] is False
    assert export["archive_committed"] is False
    assert live_update["authorised"] is False
    assert live_update["cli_upload_available"] is False
    assert live_update["native_git_integration_available"] is False
