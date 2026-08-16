"""Synthetic tests for bounded durable owner delegation."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from edn.development import (
    PROHIBITED_DELEGATED_OPERATIONS,
    DelegatedAuthorityStore,
    DelegatedGrant,
    DelegatedOperation,
    DelegatedOperationRequest,
    DelegationError,
    OwnerDelegationApproval,
)

NOW = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)


def _grant(repository: Path, **changes: object) -> DelegatedGrant:
    values: dict[str, object] = {
        "grant_id": "delegation-20260817-owner",
        "owner_id": "elliot-owner",
        "repository_root": str(repository),
        "branch": "feature/intelligence-core-v0.1",
        "starts_at": NOW,
        "expires_at": NOW + timedelta(hours=12),
        "allowed_operations": tuple(item.value for item in DelegatedOperation),
        "allowed_paths": (str(repository),),
        "allowed_source_scopes": (
            "calendar:default:category=EDN",
            "inbox:/me:folder=inbox:category=EDN:limit=25:pages=1",
            "/mnt/f/EDN OS/Working/Owner Intelligence Beta/Approved Documents",
        ),
        "provider": "openai.api",
        "model": "gpt-5-mini-2025-08-07",
        "disclosure_policy": "openai-daily-brief-pilot-v1",
        "allowed_categories": (
            "calendar.metadata",
            "engineering.metadata",
            "inbox.metadata",
            "local-files.metadata",
        ),
        "credential_mechanisms": (
            "env:EDN_OPENAI_API_KEY",
            "microsoft:browser-pkce-memory-only",
        ),
        "security_domain": "EDN",
        "classification_scheme": "edn",
        "classification_level": "confidential",
        "max_requests_per_day": 2,
        "max_successes_per_day": 1,
        "max_retries_per_day": 1,
        "max_daily_spend_aud": 2.0,
        "max_monthly_spend_aud": 20.0,
        "max_output_tokens": 2_000,
        "kill_switch_id": "owner-delegation-kill-switch",
    }
    values.update(changes)
    return DelegatedGrant(**values)  # type: ignore[arg-type]


def _store(tmp_path: Path) -> DelegatedAuthorityStore:
    return DelegatedAuthorityStore(tmp_path / "delegated-authority")


def _activate(store: DelegatedAuthorityStore, grant: DelegatedGrant) -> None:
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


def _request(grant: DelegatedGrant, **changes: object) -> DelegatedOperationRequest:
    values: dict[str, object] = {
        "operation_id": "operation-1",
        "grant_id": grant.grant_id,
        "owner_id": grant.owner_id,
        "operation": DelegatedOperation.REPOSITORY_WRITE.value,
        "repository_root": grant.repository_root,
        "branch": grant.branch,
        "requested_at": NOW + timedelta(minutes=1),
        "paths": (str(Path(grant.repository_root) / "src"),),
    }
    values.update(changes)
    return DelegatedOperationRequest(**values)  # type: ignore[arg-type]


def _pa009_request(
    grant: DelegatedGrant, **changes: object
) -> DelegatedOperationRequest:
    values: dict[str, object] = {
        "operation_id": "pa009-operation-1",
        "grant_id": grant.grant_id,
        "owner_id": grant.owner_id,
        "operation": DelegatedOperation.PA009_DISPATCH.value,
        "repository_root": grant.repository_root,
        "branch": grant.branch,
        "requested_at": NOW + timedelta(minutes=1),
        "provider": grant.provider,
        "model": grant.model,
        "disclosure_policy": grant.disclosure_policy,
        "categories": ("calendar.metadata",),
        "credential_mechanism": "env:EDN_OPENAI_API_KEY",
        "security_domain": grant.security_domain,
        "classification_scheme": grant.classification_scheme,
        "classification_level": grant.classification_level,
        "max_requests_per_day": grant.max_requests_per_day,
        "max_successes_per_day": grant.max_successes_per_day,
        "max_retries_per_day": grant.max_retries_per_day,
        "max_daily_spend_aud": grant.max_daily_spend_aud,
        "max_monthly_spend_aud": grant.max_monthly_spend_aud,
        "max_output_tokens": grant.max_output_tokens,
        "preflight_hash": "a" * 64,
        "underlying_controls_verified": True,
    }
    values.update(changes)
    return DelegatedOperationRequest(**values)  # type: ignore[arg-type]


def test_grant_persists_across_restart_and_audit_is_metadata_only(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)

    restarted = _store(tmp_path)
    claim = restarted.claim(_request(grant))
    restarted.complete(claim, now=NOW + timedelta(minutes=2))

    assert restarted.status(grant.grant_id, now=NOW) == "active"
    events = restarted.audit_events(grant.grant_id)
    assert [item[0] for item in events] == [
        "grant_activated",
        "operation_claimed",
        "operation_completed",
    ]
    serialized = repr(events)
    assert str(repository / "src") not in serialized
    assert grant.provider not in serialized


def test_expiry_revocation_and_kill_switch_fail_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    for terminal in ("expiry", "revocation", "kill"):
        grant = _grant(repository, grant_id=f"grant-{terminal}")
        store = _store(tmp_path)
        _activate(store, grant)
        if terminal == "revocation":
            store.revoke(grant.grant_id, owner_id=grant.owner_id, now=NOW)
        elif terminal == "kill":
            store.engage_kill_switch(grant.grant_id, now=NOW)
        request = _request(
            grant,
            operation_id=f"operation-{terminal}",
            requested_at=(
                grant.expires_at if terminal == "expiry" else NOW + timedelta(minutes=1)
            ),
        )
        with pytest.raises(DelegationError):
            store.claim(request)


def test_revocation_invalidates_already_claimed_operation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    claim = store.claim(_request(grant))
    store.revoke(
        grant.grant_id, owner_id=grant.owner_id, now=NOW + timedelta(minutes=2)
    )

    with pytest.raises(DelegationError, match="no longer executable"):
        store.validate_claim(claim, now=NOW + timedelta(minutes=3))


@pytest.mark.parametrize(
    "changes",
    (
        {"owner_id": "other-owner"},
        {"branch": "main"},
        {"branch": "feature/other"},
        {"repository_root": "/other/repository"},
        {"paths": ("/outside/repository",)},
        {"operation": "unknown.operation"},
        {"operation": "pa010.begin"},
    ),
)
def test_identity_branch_repository_scope_and_unknown_drift_fail_closed(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    with pytest.raises(DelegationError):
        store.claim(_request(grant, **changes))


def test_symlink_path_attack_is_denied(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repository / "linked"
    link.symlink_to(outside, target_is_directory=True)
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)

    with pytest.raises(DelegationError, match="path scope drift"):
        store.claim(_request(grant, paths=(str(link / "file.py"),)))

    with pytest.raises(DelegationError, match="path scope drift"):
        store.claim(
            _request(
                grant,
                operation_id="dotdot-operation",
                paths=(str(repository / ".." / "outside" / "file.py"),),
            )
        )


def test_tampering_fails_integrity_validation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE grants SET payload=replace(payload,"
            "'feature/intelligence-core-v0.1','main')"
        )

    with pytest.raises(DelegationError, match="integrity"):
        store.claim(_request(grant))


def test_metadata_audit_tampering_fails_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    store.claim(_request(grant))
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE audit SET reason='changed' WHERE sequence=1")

    with pytest.raises(DelegationError, match="audit integrity"):
        store.audit_events(grant.grant_id)


def test_replay_and_concurrent_double_claim_are_denied(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    request = _request(grant)

    def attempt() -> str:
        try:
            store.claim(request)
        except DelegationError:
            return "denied"
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _: attempt(), range(2)))
    assert outcomes == ["claimed", "denied"]
    with pytest.raises(DelegationError, match="replay"):
        store.claim(request)


def test_crash_leaves_claim_non_replayable(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    store.claim(_request(grant))

    with pytest.raises(DelegationError, match="replay"):
        _store(tmp_path).claim(_request(grant))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("provider", "other.provider"),
        ("model", "other-model"),
        ("categories", ("personal",)),
        ("credential_mechanism", "new-secret"),
        ("security_domain", "PERSONAL"),
        ("classification_level", "public"),
        ("max_requests_per_day", 3),
        ("max_successes_per_day", 2),
        ("max_retries_per_day", 2),
        ("max_daily_spend_aud", 3.0),
        ("max_monthly_spend_aud", 21.0),
        ("max_output_tokens", 2_001),
        ("preflight_hash", ""),
        ("underlying_controls_verified", False),
    ),
)
def test_pa009_boundary_drift_cannot_consume_delegation(
    tmp_path: Path, field: str, value: object
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    with pytest.raises(DelegationError):
        store.claim(_pa009_request(grant, **{field: value}))


def test_pa009_claim_does_not_modify_independent_budget_ledger(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    budget = tmp_path / "provider-budget.sqlite3"
    budget.write_bytes(b"independent-budget-ledger")
    before = budget.read_bytes()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)

    store.claim(_pa009_request(grant))

    assert budget.read_bytes() == before
    with sqlite3.connect(store.path) as connection:
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master")
        }
    assert "reservations" not in tables


def test_pa005_requires_exact_existing_scope_and_underlying_controls(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    valid = _request(
        grant,
        operation_id="pa005-valid",
        operation=DelegatedOperation.PA005_INBOX_READ.value,
        paths=(),
        source_scopes=("inbox:/me:folder=inbox:category=EDN:limit=25:pages=1",),
        underlying_controls_verified=True,
    )
    assert store.claim(valid).operation == DelegatedOperation.PA005_INBOX_READ.value
    with pytest.raises(DelegationError):
        store.claim(
            replace(
                valid,
                operation_id="pa005-broadened",
                source_scopes=("inbox:/me:folder=all",),
            )
        )


def test_git_requires_validation_and_exact_existing_upstream(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    request = _request(
        grant,
        operation=DelegatedOperation.GIT_PUSH.value,
        paths=(),
        validation_passed=True,
        exact_upstream=True,
    )
    assert store.claim(request).operation == DelegatedOperation.GIT_PUSH.value
    with pytest.raises(DelegationError):
        store.claim(
            replace(
                request,
                operation_id="git-invalid",
                validation_passed=False,
            )
        )


def test_unsafe_permissions_symlink_store_and_duplicate_grant_fail_closed(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    grant = _grant(repository)
    store = _store(tmp_path)
    _activate(store, grant)
    with pytest.raises(DelegationError, match="replay"):
        _activate(store, grant)
    store.root.chmod(0o755)
    with pytest.raises(DelegationError, match="unsafe"):
        store.status(grant.grant_id, now=NOW)

    store.root.chmod(0o700)
    store.path.chmod(0o644)
    with pytest.raises(DelegationError, match="unsafe"):
        store.status(grant.grant_id, now=NOW)

    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    link_root = tmp_path / "link-root"
    link_root.symlink_to(safe, target_is_directory=True)
    with pytest.raises(DelegationError, match="unsafe"):
        DelegatedAuthorityStore(link_root).status("missing", now=NOW)


def test_grant_cannot_encode_increased_limits_protected_branch_or_long_duration(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(ValueError):
        _grant(repository, max_successes_per_day=2)
    with pytest.raises(ValueError):
        _grant(repository, branch="main")
    with pytest.raises(ValueError):
        _grant(repository, expires_at=NOW + timedelta(days=8))
    with pytest.raises(ValueError):
        _grant(repository, allowed_source_scopes=("/mnt/f",))
    with pytest.raises(ValueError):
        _grant(repository, allowed_categories=("personal",))
    with pytest.raises(ValueError):
        _grant(repository, credential_mechanisms=("new-secret",))
    with pytest.raises(ValueError):
        _grant(repository, model="new-model")
    assert "pa010.begin" in PROHIBITED_DELEGATED_OPERATIONS
