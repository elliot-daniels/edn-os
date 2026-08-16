"""Tests for the non-executing delegated-authority lifecycle CLI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from edn.development import (
    DelegatedAuthorityStore,
    DelegatedGrant,
    DelegatedOperation,
    OwnerDelegationApproval,
)
from edn.development.delegation_cli import main

NOW = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
OWNER = "elliot-owner"
BRANCH = "feature/intelligence-core-v0.1"


def _grant(repository: Path) -> DelegatedGrant:
    return DelegatedGrant(
        grant_id="delegation-cli-test",
        owner_id=OWNER,
        repository_root=str(repository),
        branch=BRANCH,
        starts_at=NOW,
        expires_at=NOW + timedelta(hours=8),
        allowed_operations=tuple(item.value for item in DelegatedOperation),
        allowed_paths=(str(repository),),
        allowed_source_scopes=(
            "calendar:default:category=EDN",
            "inbox:/me:folder=inbox:category=EDN:limit=25:pages=1",
            "/mnt/f/EDN OS/Working/Owner Intelligence Beta/Approved Documents",
        ),
        provider="openai.api",
        model="gpt-5-mini-2025-08-07",
        disclosure_policy="openai-daily-brief-pilot-v1",
        allowed_categories=(
            "calendar.metadata",
            "engineering.metadata",
            "inbox.metadata",
            "local-files.metadata",
        ),
        credential_mechanisms=(
            "env:EDN_OPENAI_API_KEY",
            "microsoft:browser-pkce-memory-only",
        ),
        security_domain="EDN",
        classification_scheme="edn",
        classification_level="confidential",
        max_requests_per_day=2,
        max_successes_per_day=1,
        max_retries_per_day=1,
        max_daily_spend_aud=2.0,
        max_monthly_spend_aud=20.0,
        max_output_tokens=2_000,
        kill_switch_id="owner-delegation-kill-switch",
    )


def _active(tmp_path: Path) -> tuple[DelegatedAuthorityStore, DelegatedGrant]:
    repository = tmp_path / "repo"
    repository.mkdir(parents=True)
    store = DelegatedAuthorityStore(tmp_path / "state")
    grant = _grant(repository)
    store.activate(
        grant,
        OwnerDelegationApproval(
            grant.owner_id,
            grant.grant_id,
            grant.integrity_hash(),
            NOW,
            grant.expires_at,
        ),
        now=NOW,
    )
    return store, grant


def _base(grant: DelegatedGrant) -> list[str]:
    return [
        "--owner",
        grant.owner_id,
        "--repository",
        grant.repository_root,
        "--branch",
        grant.branch,
    ]


def test_resolve_emits_only_bounded_authority_metadata(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)

    assert main([*_base(grant), "resolve"], store=store, now=NOW) == 0

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    value = json.loads(captured.out)
    assert value == {
        "branch": grant.branch,
        "expires_at": grant.expires_at.isoformat(),
        "grant_hash": grant.integrity_hash(),
        "grant_id": grant.grant_id,
        "outcome": "active",
        "owner_id": grant.owner_id,
        "repository_root": grant.repository_root,
        "starts_at": grant.starts_at.isoformat(),
    }
    assert "credential_mechanisms" not in captured.out
    assert "allowed_source_scopes" not in captured.out


def test_claim_validate_complete_and_restart_status(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    operation_id = "repo-write-1"
    claim = [
        *_base(grant),
        "claim",
        "--operation-id",
        operation_id,
        "--operation",
        "repository.write",
        "--path",
        str(Path(grant.repository_root) / "src"),
    ]
    assert main(claim, store=store, now=NOW + timedelta(minutes=1)) == 0
    assert (
        main(
            [*_base(grant), "validate", "--operation-id", operation_id],
            store=DelegatedAuthorityStore(store.root),
            now=NOW + timedelta(minutes=2),
        )
        == 0
    )
    assert (
        main(
            [*_base(grant), "complete", "--operation-id", operation_id],
            store=DelegatedAuthorityStore(store.root),
            now=NOW + timedelta(minutes=3),
        )
        == 0
    )
    assert (
        main(
            [*_base(grant), "claim-status", "--operation-id", operation_id],
            store=DelegatedAuthorityStore(store.root),
            now=NOW + timedelta(minutes=4),
        )
        == 0
    )
    values = [json.loads(line) for line in capsys.readouterr().out.splitlines()]  # type: ignore[attr-defined]
    assert [value["outcome"] for value in values] == [
        "claimed",
        "valid",
        "completed",
        "completed",
    ]


def test_cli_claim_never_executes_claimed_repository_operation(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    target = Path(grant.repository_root) / "not-created.txt"

    assert (
        main(
            [
                *_base(grant),
                "claim",
                "--operation-id",
                "write-no-executor",
                "--operation",
                "repository.write",
                "--path",
                str(target),
            ],
            store=store,
            now=NOW + timedelta(minutes=1),
        )
        == 0
    )

    assert not target.exists()
    assert json.loads(capsys.readouterr().out)["outcome"] == "claimed"  # type: ignore[attr-defined]


def test_pa009_dispatch_requires_exact_independent_control_markers(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    base = [
        *_base(grant),
        "claim",
        "--operation",
        "pa009.dispatch",
        "--credential-mechanism",
        "env:EDN_OPENAI_API_KEY",
        "--category",
        "calendar.metadata",
    ]
    assert (
        main(
            [*base, "--operation-id", "dispatch-missing-controls"],
            store=store,
            now=NOW + timedelta(minutes=1),
        )
        == 2
    )
    capsys.readouterr()  # type: ignore[attr-defined]
    assert (
        main(
            [
                *base,
                "--operation-id",
                "dispatch-valid",
                "--preflight-hash",
                "a" * 64,
                "--underlying-controls-verified",
            ],
            store=store,
            now=NOW + timedelta(minutes=2),
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["outcome"] == "claimed"  # type: ignore[attr-defined]


def test_pa009_dispatch_rejects_noncanonical_preflight_hash(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    assert (
        main(
            [
                *_base(grant),
                "claim",
                "--operation-id",
                "dispatch-bad-hash",
                "--operation",
                "pa009.dispatch",
                "--credential-mechanism",
                "env:EDN_OPENAI_API_KEY",
                "--preflight-hash",
                "not-a-preflight-hash",
                "--underlying-controls-verified",
            ],
            store=store,
            now=NOW + timedelta(minutes=1),
        )
        == 2
    )
    assert "preflight hash is invalid" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_unknown_operation_scope_drift_and_bad_id_fail_closed(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    cases = (
        ["--operation-id", "unknown-1", "--operation", "pa010.begin"],
        [
            "--operation-id",
            "escape-1",
            "--operation",
            "repository.write",
            "--path",
            str(tmp_path / "outside"),
        ],
        [
            "--operation-id",
            "bad id",
            "--operation",
            "repository.write",
            "--path",
            grant.repository_root,
        ],
    )
    for index, options in enumerate(cases, start=1):
        assert (
            main(
                [*_base(grant), "claim", *options],
                store=store,
                now=NOW + timedelta(minutes=index),
            )
            == 2
        )
    assert capsys.readouterr().out == ""  # type: ignore[attr-defined]


def test_expiry_revocation_and_audit_tampering_block_cli(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    assert main([*_base(grant), "resolve"], store=store, now=grant.expires_at) == 2
    capsys.readouterr()  # type: ignore[attr-defined]
    store.revoke(
        grant.grant_id,
        owner_id=grant.owner_id,
        now=NOW + timedelta(minutes=1),
    )
    assert (
        main(
            [*_base(grant), "resolve"],
            store=store,
            now=NOW + timedelta(minutes=2),
        )
        == 2
    )

    second_store, second_grant = _active(tmp_path / "second")
    with sqlite3.connect(second_store.path) as connection:
        connection.execute("UPDATE audit SET reason='tampered' WHERE sequence=1")
    assert (
        main(
            [*_base(second_grant), "resolve"],
            store=second_store,
            now=NOW + timedelta(minutes=1),
        )
        == 2
    )


def test_completed_or_missing_claim_cannot_be_completed_again(
    tmp_path: Path, capsys: object
) -> None:
    store, grant = _active(tmp_path)
    operation_id = "static-1"
    assert (
        main(
            [
                *_base(grant),
                "claim",
                "--operation-id",
                operation_id,
                "--operation",
                "validation.static",
            ],
            store=store,
            now=NOW + timedelta(minutes=1),
        )
        == 0
    )
    assert (
        main(
            [*_base(grant), "complete", "--operation-id", operation_id],
            store=store,
            now=NOW + timedelta(minutes=2),
        )
        == 0
    )
    assert (
        main(
            [*_base(grant), "complete", "--operation-id", operation_id],
            store=store,
            now=NOW + timedelta(minutes=3),
        )
        == 2
    )
    assert (
        main(
            [*_base(grant), "claim-status", "--operation-id", "missing"],
            store=store,
            now=NOW + timedelta(minutes=4),
        )
        == 2
    )
    assert "traceback" not in capsys.readouterr().err.lower()  # type: ignore[attr-defined]
