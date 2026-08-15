"""Protected, sanitised PA-009 owner-review result handoff tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edn.core import Classification
from edn.intelligence import (
    ModelResponse,
    ModelStatement,
    ModelStatementKind,
    OwnerReviewResultStore,
    ProviderResultStoreError,
)

NOW = datetime(2026, 8, 15, tzinfo=UTC)
CLASSIFICATION = Classification("edn", "confidential", "EDN Confidential", 2)
HASH = "a" * 64


def _response() -> ModelResponse:
    return ModelResponse(
        "result-request-1",
        "openai.api",
        (
            ModelStatement(
                ModelStatementKind.MODEL_ASSERTION,
                "A bounded model assertion for owner review.",
                ("disclosed-1",),
                "Model-derived and not verified fact.",
                "openai.api",
                False,
            ),
            ModelStatement(
                ModelStatementKind.EVIDENCE_GAP,
                "A relevant source is not represented.",
                ("disclosed-2",),
                None,
                "openai.api",
                False,
            ),
            ModelStatement(
                ModelStatementKind.PROPOSED_ACTION,
                "Review the cited metadata locally.",
                ("disclosed-1", "disclosed-2"),
                "Owner approval remains required.",
                "openai.api",
                True,
            ),
        ),
        ("disclosed-1", "disclosed-2"),
    )


def _persist(root: Path) -> tuple[OwnerReviewResultStore, object]:
    store = OwnerReviewResultStore(root)
    result = store.persist_validated(
        _response(),
        preflight_hash=HASH,
        model="gpt-5-mini-2025-08-07",
        disclosure_policy="openai-daily-brief-pilot-v1",
        security_domain="EDN",
        classification=CLASSIFICATION,
        validated_evidence_ids=frozenset({"disclosed-1", "disclosed-2"}),
        created_at=NOW,
    )
    return store, result


def test_validated_result_persists_and_survives_process_restart(tmp_path: Path) -> None:
    root = tmp_path / "provider-results"
    store, expected = _persist(root)
    path = next(root.glob("*.json"))

    assert oct(root.stat().st_mode & 0o777) == "0o700"
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert root.stat().st_uid == os.geteuid() == path.stat().st_uid
    assert store.load("result-request-1", now=NOW) == expected
    code = (
        "import json,sys; from datetime import datetime; from pathlib import Path; "
        "from edn.intelligence import OwnerReviewResultStore; "
        "r=OwnerReviewResultStore(Path(sys.argv[1])).load("
        "sys.argv[2],now=datetime.fromisoformat(sys.argv[3])); "
        "print(json.dumps([[s.kind.value,s.text,"
        "list(s.disclosed_evidence_ids),s.uncertainty,s.proposal_only] "
        "for s in r.statements]))"
    )
    output = subprocess.check_output(
        [sys.executable, "-c", code, str(root), "result-request-1", NOW.isoformat()],
        text=True,
    )
    assert json.loads(output)[2] == [
        "proposed_action",
        "Review the cited metadata locally.",
        ["disclosed-1", "disclosed-2"],
        "Owner approval remains required.",
        True,
    ]


def test_owner_review_preserves_types_uncertainty_citations_and_proposal_boundary(
    tmp_path: Path,
) -> None:
    store, _ = _persist(tmp_path / "provider-results")
    result = store.load("result-request-1", now=NOW)
    grouped = result.grouped_statements()

    assert grouped[ModelStatementKind.MODEL_ASSERTION][0].text == (
        "A bounded model assertion for owner review."
    )
    assert grouped[ModelStatementKind.MODEL_ASSERTION][0].uncertainty == (
        "Model-derived and not verified fact."
    )
    assert grouped[ModelStatementKind.EVIDENCE_GAP][0].disclosed_evidence_ids == (
        "disclosed-2",
    )
    action = grouped[ModelStatementKind.PROPOSED_ACTION][0]
    assert action.proposal_only is True
    assert not hasattr(store, "approve")
    assert not hasattr(store, "dispatch")
    assert not hasattr(store, "preflight")


def test_serialized_result_is_closed_and_excludes_prohibited_data(
    tmp_path: Path,
) -> None:
    root = tmp_path / "provider-results"
    _persist(root)
    document = json.loads(next(root.glob("*.json")).read_text())

    assert set(document) == {
        "schema_version", "request_id", "preflight_hash", "provider", "model",
        "disclosure_policy", "security_domain", "classification", "created_at",
        "expires_at", "schema_validation", "citation_validation", "statements",
        "integrity_hash",
    }
    serialized = json.dumps(document)
    for prohibited in (
        "raw_response", "prompt", "projection", "source_content", "email_body",
        "credential", "authorization", "api_key", "approval_token", "headers",
    ):
        assert f'"{prohibited}"' not in serialized
    assert "synthetic projection secret" not in serialized


def test_tampering_duplicate_and_unsafe_permissions_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "provider-results"
    store, _ = _persist(root)
    path = next(root.glob("*.json"))
    with pytest.raises(ProviderResultStoreError, match="already exists"):
        _persist(root)

    value = json.loads(path.read_text())
    value["statements"][0]["text"] = "tampered"
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    path.chmod(0o600)
    with pytest.raises(ProviderResultStoreError, match="integrity"):
        store.load("result-request-1", now=NOW)

    path.chmod(0o644)
    with pytest.raises(ProviderResultStoreError, match="mode"):
        store.load("result-request-1", now=NOW)


def test_symlink_paths_and_citation_mismatch_fail_closed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    _persist(real)
    unsafe = tmp_path / "unsafe"
    unsafe.symlink_to(real, target_is_directory=True)
    with pytest.raises(ProviderResultStoreError, match="path type"):
        OwnerReviewResultStore(unsafe).load("result-request-1", now=NOW)

    target = tmp_path / "target.json"
    target.write_text("{}")
    root = tmp_path / "new-results"
    root.mkdir(mode=0o700)
    result_path = root / __import__("hashlib").sha256(
        b"result-request-1"
    ).hexdigest()
    result_path = result_path.with_suffix(".json")
    result_path.symlink_to(target)
    with pytest.raises(ProviderResultStoreError, match="already exists"):
        _persist(root)

    with pytest.raises(ProviderResultStoreError, match="evidence binding"):
        OwnerReviewResultStore(tmp_path / "citation").persist_validated(
            _response(),
            preflight_hash=HASH,
            model="gpt-5-mini-2025-08-07",
            disclosure_policy="openai-daily-brief-pilot-v1",
            security_domain="EDN",
            classification=CLASSIFICATION,
            validated_evidence_ids=frozenset({"disclosed-1"}),
            created_at=NOW,
        )


def test_expiry_fails_closed_and_removes_result_without_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "provider-results"
    store, _ = _persist(root)
    with pytest.raises(ProviderResultStoreError, match="expired"):
        store.load("result-request-1", now=NOW + timedelta(days=31))
    assert not tuple(root.glob("*.json"))


def test_bounds_and_only_passed_validation_are_constructible(tmp_path: Path) -> None:
    store = OwnerReviewResultStore(tmp_path / "provider-results")
    oversized = replace(
        _response(),
        statements=(
            ModelStatement(
                ModelStatementKind.MODEL_ASSERTION,
                "x" * 2_001,
                ("disclosed-1",),
                None,
                "openai.api",
                False,
            ),
        ),
    )
    with pytest.raises(ProviderResultStoreError, match="sanitisation"):
        store.persist_validated(
            oversized,
            preflight_hash=HASH,
            model="gpt-5-mini-2025-08-07",
            disclosure_policy="openai-daily-brief-pilot-v1",
            security_domain="EDN",
            classification=CLASSIFICATION,
            validated_evidence_ids=frozenset({"disclosed-1", "disclosed-2"}),
            created_at=NOW,
        )
