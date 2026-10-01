import json
from pathlib import Path

import pytest

from edn.connectors.local_files.cli import _load_approval, _load_selection


def test_selection_requires_unique_bounded_exact_candidate_ids(tmp_path: Path) -> None:
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(["candidate:one", "candidate:two"]), encoding="utf-8"
    )

    assert _load_selection(selection) == ("candidate:one", "candidate:two")

    selection.write_text(
        json.dumps(["candidate:one", "candidate:one"]), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unique"):
        _load_selection(selection)


def test_ingestion_approval_file_is_strict_and_expiring(tmp_path: Path) -> None:
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "approval_ref": "approval:pa005",
                "plan_id": "plan:pa005",
                "plan_hash": "a" * 64,
                "scope": ["candidate:one"],
                "expires_at": "2026-08-13T11:00:00+09:30",
            }
        ),
        encoding="utf-8",
    )

    binding = _load_approval(approval)

    assert binding.scope == ("candidate:one",)
    assert binding.expires_at is not None

    value = json.loads(approval.read_text(encoding="utf-8"))
    value["unexpected"] = True
    approval.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="shape"):
        _load_approval(approval)
