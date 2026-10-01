"""Narrow CLI for durable delegated-authority claim lifecycle operations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from edn.development.delegation import (
    DelegatedAuthorityStore,
    DelegatedGrant,
    DelegatedOperation,
    DelegatedOperationRequest,
    DelegationError,
)

_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_PREFLIGHT_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PATH_OPERATIONS = {
    DelegatedOperation.REPOSITORY_READ.value,
    DelegatedOperation.REPOSITORY_WRITE.value,
}
_GIT_OPERATIONS = {
    DelegatedOperation.GIT_STAGE.value,
    DelegatedOperation.GIT_COMMIT.value,
    DelegatedOperation.GIT_PUSH.value,
}
_PA005_OPERATIONS = {
    DelegatedOperation.PA005_CALENDAR_READ.value,
    DelegatedOperation.PA005_INBOX_READ.value,
    DelegatedOperation.PA005_LOCAL_FILES_READ.value,
}
_PA009_OPERATIONS = {
    DelegatedOperation.PA009_BUDGET_CHECK.value,
    DelegatedOperation.PA009_CREDENTIAL_CHECK.value,
    DelegatedOperation.PA009_PREFLIGHT.value,
    DelegatedOperation.PA009_DISPATCH.value,
    DelegatedOperation.PA009_RESULT_REVIEW.value,
}


def main(
    argv: Sequence[str] | None = None,
    *,
    store: DelegatedAuthorityStore | None = None,
    now: datetime | None = None,
) -> int:
    """Run a metadata-only grant/claim operation; never execute the claimed work."""

    args = _parser().parse_args(argv)
    instant = now or datetime.now(UTC)
    authority = store or DelegatedAuthorityStore()
    try:
        grant = authority.resolve_active(
            owner_id=args.owner,
            repository_root=str(Path(args.repository).absolute()),
            branch=args.branch,
            now=instant,
        )
        authority.audit_events(grant.grant_id)
        if args.command == "resolve":
            _emit(
                {
                    "branch": grant.branch,
                    "expires_at": grant.expires_at.astimezone(UTC).isoformat(),
                    "grant_hash": grant.integrity_hash(),
                    "grant_id": grant.grant_id,
                    "outcome": "active",
                    "owner_id": grant.owner_id,
                    "repository_root": grant.repository_root,
                    "starts_at": grant.starts_at.astimezone(UTC).isoformat(),
                }
            )
            return 0
        operation_id = _valid_operation_id(args.operation_id)
        if args.command == "claim":
            claim = authority.claim(_request(args, grant, operation_id, instant))
            authority.validate_claim(claim, now=instant)
            _emit(
                {
                    "grant_id": claim.grant_id,
                    "operation": claim.operation,
                    "operation_id": claim.operation_id,
                    "outcome": "claimed",
                }
            )
            return 0
        record = authority.claim_record(operation_id)
        if record.claim.grant_id != grant.grant_id:
            raise DelegationError("delegated claim does not match active session")
        if args.command == "validate":
            authority.validate_claim(record.claim, now=instant)
            outcome = "valid"
        elif args.command == "complete":
            authority.validate_claim(record.claim, now=instant)
            authority.complete(record.claim, now=instant)
            outcome = "completed"
        else:
            outcome = record.state
        _emit(
            {
                "grant_id": record.claim.grant_id,
                "operation": record.claim.operation,
                "operation_id": record.claim.operation_id,
                "outcome": outcome,
            }
        )
        return 0
    except (DelegationError, ValueError, OSError) as exc:
        _emit({"outcome": "blocked", "reason": str(exc)}, stream=sys.stderr)
        return 2


def _request(
    args: argparse.Namespace,
    grant: DelegatedGrant,
    operation_id: str,
    now: datetime,
) -> DelegatedOperationRequest:
    try:
        operation = DelegatedOperation(args.operation).value
    except ValueError as exc:
        raise DelegationError("delegated operation is unknown") from exc
    paths = tuple(args.path)
    source_scopes = tuple(args.source_scope)
    categories = tuple(args.category)
    if operation in _PATH_OPERATIONS and not paths:
        raise DelegationError("delegated repository path is missing")
    if operation in _GIT_OPERATIONS and not (
        args.validation_passed and args.exact_upstream
    ):
        raise DelegationError("delegated Git preconditions failed")
    if operation in _PA005_OPERATIONS and not (
        source_scopes and args.underlying_controls_verified
    ):
        raise DelegationError("delegated PA-005 controls missing")
    if operation in _PA009_OPERATIONS and not (
        args.credential_mechanism and args.underlying_controls_verified
    ):
        raise DelegationError("delegated PA-009 controls missing")
    if operation == DelegatedOperation.PA009_DISPATCH.value and not (
        args.preflight_hash and _PREFLIGHT_HASH.fullmatch(args.preflight_hash)
    ):
        raise DelegationError("delegated PA-009 preflight hash is invalid")
    return DelegatedOperationRequest(
        operation_id=operation_id,
        grant_id=grant.grant_id,
        owner_id=grant.owner_id,
        operation=operation,
        repository_root=grant.repository_root,
        branch=grant.branch,
        requested_at=now,
        paths=paths,
        source_scopes=source_scopes,
        provider=grant.provider if operation in _PA009_OPERATIONS else "",
        model=grant.model if operation in _PA009_OPERATIONS else "",
        disclosure_policy=(
            grant.disclosure_policy if operation in _PA009_OPERATIONS else ""
        ),
        categories=categories,
        credential_mechanism=args.credential_mechanism,
        security_domain=grant.security_domain if operation in _PA009_OPERATIONS else "",
        classification_scheme=(
            grant.classification_scheme if operation in _PA009_OPERATIONS else ""
        ),
        classification_level=(
            grant.classification_level if operation in _PA009_OPERATIONS else ""
        ),
        max_requests_per_day=(
            grant.max_requests_per_day if operation in _PA009_OPERATIONS else 0
        ),
        max_successes_per_day=(
            grant.max_successes_per_day if operation in _PA009_OPERATIONS else 0
        ),
        max_retries_per_day=(
            grant.max_retries_per_day if operation in _PA009_OPERATIONS else 0
        ),
        max_daily_spend_aud=(
            grant.max_daily_spend_aud if operation in _PA009_OPERATIONS else 0.0
        ),
        max_monthly_spend_aud=(
            grant.max_monthly_spend_aud if operation in _PA009_OPERATIONS else 0.0
        ),
        max_output_tokens=(
            grant.max_output_tokens if operation in _PA009_OPERATIONS else 0
        ),
        preflight_hash=args.preflight_hash,
        underlying_controls_verified=args.underlying_controls_verified,
        validation_passed=args.validation_passed,
        exact_upstream=args.exact_upstream,
    )


def _valid_operation_id(value: str) -> str:
    if not _OPERATION_ID.fullmatch(value):
        raise DelegationError("delegated operation ID is invalid")
    return value


def _emit(value: dict[str, object], *, stream: TextIO | None = None) -> None:
    destination = stream or sys.stdout
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--branch", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("resolve")
    claim = commands.add_parser("claim")
    claim.add_argument("--operation-id", required=True)
    claim.add_argument("--operation", required=True)
    claim.add_argument("--path", action="append", default=[])
    claim.add_argument("--source-scope", action="append", default=[])
    claim.add_argument("--category", action="append", default=[])
    claim.add_argument("--credential-mechanism", default="")
    claim.add_argument("--preflight-hash", default="")
    claim.add_argument("--underlying-controls-verified", action="store_true")
    claim.add_argument("--validation-passed", action="store_true")
    claim.add_argument("--exact-upstream", action="store_true")
    for command in ("validate", "complete", "claim-status"):
        action = commands.add_parser(command)
        action.add_argument("--operation-id", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
