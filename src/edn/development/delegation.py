"""Protected, bounded owner delegation for repetitive EDN OS operations."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any


class DelegationError(RuntimeError):
    """A delegated grant or operation failed closed."""


class DelegatedOperation(StrEnum):
    REPOSITORY_READ = "repository.read"
    REPOSITORY_WRITE = "repository.write"
    TEST = "validation.pytest"
    LINT = "validation.ruff"
    TYPE_CHECK = "validation.mypy"
    STATIC_VALIDATE = "validation.static"
    GIT_STAGE = "git.stage.validated_increment"
    GIT_COMMIT = "git.commit.validated_increment"
    GIT_PUSH = "git.push.current_upstream"
    PA005_CALENDAR_READ = "pa005.calendar.read"
    PA005_INBOX_READ = "pa005.inbox.read"
    PA005_LOCAL_FILES_READ = "pa005.local-files.read"
    PA009_BUDGET_CHECK = "pa009.budget.check"
    PA009_CREDENTIAL_CHECK = "pa009.credential.check"
    PA009_PREFLIGHT = "pa009.preflight"
    PA009_DISPATCH = "pa009.dispatch"
    PA009_RESULT_REVIEW = "pa009.result.review"


PROHIBITED_DELEGATED_OPERATIONS = frozenset(
    {
        "credential.create",
        "credential.scope.change",
        "microsoft.permission.change",
        "data.source.add",
        "disclosure.category.expand",
        "security.control.weaken",
        "budget.limit.increase",
        "git.merge",
        "git.rebase",
        "git.push.force",
        "git.protected.modify",
        "external.notify",
        "external.deliver",
        "external.destructive",
        "financial.purchase",
        "production.deploy",
        "secret.long_lived.create",
        "pa010.begin",
    }
)
APPROVED_DELEGATED_SOURCE_SCOPES = frozenset(
    {
        "calendar:default:category=EDN",
        "inbox:/me:folder=inbox:category=EDN:limit=25:pages=1",
        "/mnt/f/EDN OS/Working/Owner Intelligence Beta/Approved Documents",
    }
)
APPROVED_DELEGATED_CATEGORIES = frozenset(
    {
        "calendar.metadata",
        "engineering.metadata",
        "inbox.metadata",
        "local-files.metadata",
    }
)
APPROVED_CREDENTIAL_MECHANISMS = frozenset(
    {
        "env:EDN_OPENAI_API_KEY",
        "microsoft:browser-pkce-memory-only",
    }
)


@dataclass(frozen=True, slots=True)
class DelegatedGrant:
    grant_id: str
    owner_id: str
    repository_root: str
    branch: str
    starts_at: datetime
    expires_at: datetime
    allowed_operations: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    allowed_source_scopes: tuple[str, ...]
    provider: str
    model: str
    disclosure_policy: str
    allowed_categories: tuple[str, ...]
    credential_mechanisms: tuple[str, ...]
    security_domain: str
    classification_scheme: str
    classification_level: str
    max_requests_per_day: int
    max_successes_per_day: int
    max_retries_per_day: int
    max_daily_spend_aud: float
    max_monthly_spend_aud: float
    max_output_tokens: int
    kill_switch_id: str

    def __post_init__(self) -> None:
        if (
            not self.grant_id
            or not self.owner_id
            or not self.branch.startswith("feature/")
            or self.starts_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.starts_at
            or not self.allowed_operations
            or not self.kill_switch_id
        ):
            raise ValueError("delegated grant binding is invalid")
        if self.expires_at - self.starts_at > _MAX_GRANT_DURATION:
            raise ValueError("delegated grant duration exceeds seven days")
        unknown = set(self.allowed_operations) - {
            item.value for item in DelegatedOperation
        }
        if unknown or set(self.allowed_operations) & PROHIBITED_DELEGATED_OPERATIONS:
            raise ValueError("delegated operation is unknown or prohibited")
        root = Path(self.repository_root)
        if not root.is_absolute() or not self.allowed_paths:
            raise ValueError("delegated repository paths must be absolute and bounded")
        if any(not _is_within(Path(value), root) for value in self.allowed_paths):
            raise ValueError("delegated path escapes repository")
        if (
            self.max_requests_per_day != 2
            or self.max_successes_per_day != 1
            or self.max_retries_per_day != 1
            or self.max_daily_spend_aud != 2.0
            or self.max_monthly_spend_aud != 20.0
            or self.max_output_tokens != 2_000
        ):
            raise ValueError("delegation cannot alter PA-009 limits")
        if (
            not set(self.allowed_source_scopes) <= APPROVED_DELEGATED_SOURCE_SCOPES
            or not set(self.allowed_categories) <= APPROVED_DELEGATED_CATEGORIES
            or not set(self.credential_mechanisms) <= APPROVED_CREDENTIAL_MECHANISMS
            or self.provider != "openai.api"
            or self.model != "gpt-5-mini-2025-08-07"
            or self.disclosure_policy != "openai-daily-brief-pilot-v1"
            or self.security_domain != "EDN"
            or self.classification_scheme != "edn"
            or self.classification_level != "confidential"
        ):
            raise ValueError("delegation cannot broaden existing source/provider scope")

    def canonical_payload(self) -> dict[str, object]:
        value = asdict(self)
        value["starts_at"] = self.starts_at.astimezone(UTC).isoformat()
        value["expires_at"] = self.expires_at.astimezone(UTC).isoformat()
        return value

    def integrity_hash(self) -> str:
        return hashlib.sha256(_canonical(self.canonical_payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class OwnerDelegationApproval:
    owner_id: str
    grant_id: str
    grant_hash: str
    approved_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class DelegatedOperationRequest:
    operation_id: str
    grant_id: str
    owner_id: str
    operation: str
    repository_root: str
    branch: str
    requested_at: datetime
    paths: tuple[str, ...] = ()
    source_scopes: tuple[str, ...] = ()
    provider: str = ""
    model: str = ""
    disclosure_policy: str = ""
    categories: tuple[str, ...] = ()
    credential_mechanism: str = ""
    security_domain: str = ""
    classification_scheme: str = ""
    classification_level: str = ""
    max_requests_per_day: int = 0
    max_successes_per_day: int = 0
    max_retries_per_day: int = 0
    max_daily_spend_aud: float = 0.0
    max_monthly_spend_aud: float = 0.0
    max_output_tokens: int = 0
    preflight_hash: str = ""
    underlying_controls_verified: bool = False
    validation_passed: bool = False
    exact_upstream: bool = False


@dataclass(frozen=True, slots=True)
class DelegatedClaim:
    grant_id: str
    operation_id: str
    operation: str
    claimed_at: datetime


_MAX_GRANT_DURATION = timedelta(days=7)
_PA009_OPERATIONS = frozenset(
    {
        DelegatedOperation.PA009_BUDGET_CHECK.value,
        DelegatedOperation.PA009_CREDENTIAL_CHECK.value,
        DelegatedOperation.PA009_PREFLIGHT.value,
        DelegatedOperation.PA009_DISPATCH.value,
        DelegatedOperation.PA009_RESULT_REVIEW.value,
    }
)
_GIT_OPERATIONS = frozenset(
    {
        DelegatedOperation.GIT_STAGE.value,
        DelegatedOperation.GIT_COMMIT.value,
        DelegatedOperation.GIT_PUSH.value,
    }
)
_PA005_OPERATIONS = frozenset(
    {
        DelegatedOperation.PA005_CALENDAR_READ.value,
        DelegatedOperation.PA005_INBOX_READ.value,
        DelegatedOperation.PA005_LOCAL_FILES_READ.value,
    }
)
_PATH_OPERATIONS = frozenset(
    {
        DelegatedOperation.REPOSITORY_READ.value,
        DelegatedOperation.REPOSITORY_WRITE.value,
    }
)


class DelegatedAuthorityStore:
    """Owner-only SQLite grant state and metadata-only operation ledger."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_root()
        self.path = self.root / "delegated-authority.sqlite3"

    def activate(
        self, grant: DelegatedGrant, approval: OwnerDelegationApproval, *, now: datetime
    ) -> str:
        digest = grant.integrity_hash()
        if (
            now.tzinfo is None
            or approval.approved_at.tzinfo is None
            or approval.expires_at.tzinfo is None
            or approval.owner_id != grant.owner_id
            or approval.grant_id != grant.grant_id
            or approval.grant_hash != digest
            or approval.expires_at != grant.expires_at
            or not (approval.approved_at <= now < grant.expires_at)
        ):
            raise DelegationError("owner delegation approval is invalid")
        payload = _canonical(grant.canonical_payload()).decode()
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO grants(grant_id,payload,integrity_hash,state,"
                    "created_at) "
                    "VALUES(?,?,?,?,?)",
                    (grant.grant_id, payload, digest, "active", _time(now)),
                )
                self._audit(connection, grant.grant_id, "grant_activated", now)
            except sqlite3.IntegrityError as exc:
                raise DelegationError("delegated grant replay is denied") from exc
            connection.commit()
        return digest

    def claim(self, request: DelegatedOperationRequest) -> DelegatedClaim:
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            grant, state = self._load(connection, request.grant_id)
            reason = self._denial_reason(connection, grant, state, request)
            if reason is not None:
                self._audit(
                    connection,
                    request.grant_id,
                    "operation_denied",
                    request.requested_at,
                    reason,
                )
                connection.commit()
                raise DelegationError(reason)
            try:
                connection.execute(
                    "INSERT INTO claims(operation_id,grant_id,operation,state,"
                    "claimed_at) "
                    "VALUES(?,?,?,?,?)",
                    (
                        request.operation_id,
                        request.grant_id,
                        request.operation,
                        "claimed",
                        _time(request.requested_at),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise DelegationError("delegated operation replay is denied") from exc
            self._audit(
                connection,
                request.grant_id,
                "operation_claimed",
                request.requested_at,
                request.operation,
            )
            connection.commit()
        return DelegatedClaim(
            request.grant_id,
            request.operation_id,
            request.operation,
            request.requested_at,
        )

    def complete(self, claim: DelegatedClaim, *, now: datetime) -> None:
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            grant, state = self._load(connection, claim.grant_id)
            if state != "active" or not (grant.starts_at <= now < grant.expires_at):
                raise DelegationError("delegated claim is no longer executable")
            changed = connection.execute(
                "UPDATE claims SET state='completed',completed_at=? "
                "WHERE operation_id=? AND grant_id=? AND operation=? "
                "AND state='claimed'",
                (_time(now), claim.operation_id, claim.grant_id, claim.operation),
            ).rowcount
            if changed != 1:
                raise DelegationError("delegated claim is missing or terminal")
            self._audit(
                connection, claim.grant_id, "operation_completed", now, claim.operation
            )
            connection.commit()

    def validate_claim(self, claim: DelegatedClaim, *, now: datetime) -> None:
        """Recheck a claim immediately before its local or bounded operation."""

        with closing(self._connection()) as connection:
            grant, state = self._load(connection, claim.grant_id)
            row = connection.execute(
                "SELECT operation,state FROM claims WHERE operation_id=? "
                "AND grant_id=?",
                (claim.operation_id, claim.grant_id),
            ).fetchone()
        if (
            state != "active"
            or not (grant.starts_at <= now < grant.expires_at)
            or row is None
            or str(row[0]) != claim.operation
            or str(row[1]) != "claimed"
        ):
            raise DelegationError("delegated claim is no longer executable")

    def revoke(self, grant_id: str, *, owner_id: str, now: datetime) -> None:
        self._terminal(grant_id, owner_id=owner_id, now=now, state="revoked")

    def engage_kill_switch(self, grant_id: str, *, now: datetime) -> None:
        self._terminal(grant_id, owner_id=None, now=now, state="killed")

    def status(self, grant_id: str, *, now: datetime) -> str:
        with closing(self._connection()) as connection:
            grant, state = self._load(connection, grant_id)
        if state == "active" and now >= grant.expires_at:
            return "expired"
        return state

    def audit_events(self, grant_id: str) -> tuple[tuple[str, str, str], ...]:
        with closing(self._connection()) as connection:
            rows = connection.execute(
                "SELECT sequence,event_type,reason,timestamp,previous_hash,event_hash "
                "FROM audit WHERE grant_id=? "
                "ORDER BY sequence",
                (grant_id,),
            ).fetchall()
        previous = ""
        events: list[tuple[str, str, str]] = []
        for sequence, event_type, reason, timestamp, previous_hash, event_hash in rows:
            value = {
                "sequence": int(sequence),
                "grant_id": grant_id,
                "event_type": str(event_type),
                "reason": str(reason),
                "timestamp": str(timestamp),
                "previous_hash": str(previous_hash),
            }
            expected = hashlib.sha256(_canonical(value)).hexdigest()
            if str(previous_hash) != previous or str(event_hash) != expected:
                raise DelegationError("delegated audit integrity failure")
            previous = expected
            events.append((str(event_type), str(reason), str(timestamp)))
        return tuple(events)

    def _terminal(
        self, grant_id: str, *, owner_id: str | None, now: datetime, state: str
    ) -> None:
        with closing(self._connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            grant, current = self._load(connection, grant_id)
            if owner_id is not None and owner_id != grant.owner_id:
                raise DelegationError("delegated owner identity mismatch")
            if current != "active":
                raise DelegationError("delegated grant is already terminal")
            connection.execute(
                "UPDATE grants SET state=?,terminal_at=? WHERE grant_id=?",
                (state, _time(now), grant_id),
            )
            self._audit(connection, grant_id, f"grant_{state}", now)
            connection.commit()

    def _denial_reason(
        self,
        connection: sqlite3.Connection,
        grant: DelegatedGrant,
        state: str,
        request: DelegatedOperationRequest,
    ) -> str | None:
        del connection
        if request.requested_at.tzinfo is None:
            return "delegated operation time is invalid"
        if state != "active":
            return "delegated grant is not active"
        if not (grant.starts_at <= request.requested_at < grant.expires_at):
            return "delegated grant is not within its active window"
        if request.owner_id != grant.owner_id:
            return "delegated owner identity mismatch"
        if request.operation in PROHIBITED_DELEGATED_OPERATIONS:
            return "operation is permanently prohibited"
        if request.operation not in grant.allowed_operations:
            return "operation is outside delegated scope"
        if (
            request.repository_root != grant.repository_root
            or request.branch != grant.branch
            or request.branch in {"main", "master"}
            or request.branch.startswith(("protected/", "release/"))
        ):
            return "repository or branch drift"
        if any(
            not any(_is_within(Path(path), Path(root)) for root in grant.allowed_paths)
            or _has_symlink_component(Path(path), Path(grant.repository_root))
            for path in request.paths
        ):
            return "delegated path scope drift"
        if not set(request.source_scopes) <= set(grant.allowed_source_scopes):
            return "delegated source scope drift"
        if request.operation in _PATH_OPERATIONS and not request.paths:
            return "delegated repository path is missing"
        if request.operation in _PA005_OPERATIONS and (
            not request.source_scopes or not request.underlying_controls_verified
        ):
            return "delegated PA-005 controls missing"
        if request.operation in _GIT_OPERATIONS and not (
            request.validation_passed and request.exact_upstream
        ):
            return "delegated Git preconditions failed"
        if request.operation in _PA009_OPERATIONS:
            if not self._pa009_matches(grant, request):
                return "delegated PA-009 boundary drift"
            if request.operation == DelegatedOperation.PA009_DISPATCH.value and (
                not request.preflight_hash or not request.underlying_controls_verified
            ):
                return "delegated PA-009 dispatch controls missing"
        return None

    @staticmethod
    def _pa009_matches(
        grant: DelegatedGrant, request: DelegatedOperationRequest
    ) -> bool:
        return (
            request.provider == grant.provider
            and request.model == grant.model
            and request.disclosure_policy == grant.disclosure_policy
            and set(request.categories) <= set(grant.allowed_categories)
            and request.credential_mechanism in grant.credential_mechanisms
            and request.security_domain == grant.security_domain
            and request.classification_scheme == grant.classification_scheme
            and request.classification_level == grant.classification_level
            and request.max_requests_per_day == grant.max_requests_per_day
            and request.max_successes_per_day == grant.max_successes_per_day
            and request.max_retries_per_day == grant.max_retries_per_day
            and request.max_daily_spend_aud == grant.max_daily_spend_aud
            and request.max_monthly_spend_aud == grant.max_monthly_spend_aud
            and request.max_output_tokens == grant.max_output_tokens
            and request.underlying_controls_verified
        )

    def _load(
        self, connection: sqlite3.Connection, grant_id: str
    ) -> tuple[DelegatedGrant, str]:
        row = connection.execute(
            "SELECT payload,integrity_hash,state FROM grants WHERE grant_id=?",
            (grant_id,),
        ).fetchone()
        if row is None:
            raise DelegationError("delegated grant is unavailable")
        payload, digest, state = str(row[0]), str(row[1]), str(row[2])
        if hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise DelegationError("delegated grant integrity failure")
        try:
            value = json.loads(payload)
            if not isinstance(value, dict) or _canonical(value).decode() != payload:
                raise ValueError
            grant = _grant(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise DelegationError("delegated grant is corrupt") from exc
        if grant.integrity_hash() != digest:
            raise DelegationError("delegated grant binding failure")
        return grant, state

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        grant_id: str,
        event_type: str,
        now: datetime,
        reason: str = "",
    ) -> None:
        previous_row = connection.execute(
            "SELECT event_hash FROM audit WHERE grant_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (grant_id,),
        ).fetchone()
        previous = "" if previous_row is None else str(previous_row[0])
        next_sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM audit"
            ).fetchone()[0]
        )
        timestamp = _time(now)
        event_hash = hashlib.sha256(
            _canonical(
                {
                    "sequence": next_sequence,
                    "grant_id": grant_id,
                    "event_type": event_type,
                    "reason": reason,
                    "timestamp": timestamp,
                    "previous_hash": previous,
                }
            )
        ).hexdigest()
        connection.execute(
            "INSERT INTO audit(sequence,grant_id,event_type,reason,timestamp,"
            "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)",
            (
                next_sequence,
                grant_id,
                event_type,
                reason,
                timestamp,
                previous,
                event_hash,
            ),
        )

    def _connection(self) -> sqlite3.Connection:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = self.root.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
            or self.path.is_symlink()
        ):
            raise DelegationError("delegated authority path is unsafe")
        if self.path.exists():
            existing = self.path.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(existing.st_mode)
                or existing.st_uid != os.geteuid()
                or stat.S_IMODE(existing.st_mode) != 0o600
            ):
                raise DelegationError("delegated authority ownership or mode is unsafe")
        else:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(self.path, flags, 0o600)
            except FileExistsError as exc:
                raise DelegationError("delegated authority path race detected") from exc
            os.close(descriptor)
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        file_stat = self.path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or stat.S_IMODE(file_stat.st_mode) != 0o600
        ):
            connection.close()
            raise DelegationError("delegated authority ownership or mode is unsafe")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS grants(grant_id TEXT PRIMARY KEY,payload TEXT "
            "NOT NULL,integrity_hash TEXT NOT NULL,state TEXT NOT NULL,created_at TEXT "
            "NOT NULL,terminal_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS claims(operation_id TEXT PRIMARY KEY,grant_id "
            "TEXT NOT NULL,operation TEXT NOT NULL,state TEXT NOT NULL,claimed_at TEXT "
            "NOT NULL,completed_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY,"
            "grant_id TEXT NOT NULL,event_type TEXT NOT NULL,reason TEXT NOT NULL,"
            "timestamp TEXT NOT NULL,previous_hash TEXT NOT NULL,"
            "event_hash TEXT NOT NULL)"
        )
        return connection


def _grant(value: dict[str, Any]) -> DelegatedGrant:
    return DelegatedGrant(
        str(value["grant_id"]),
        str(value["owner_id"]),
        str(value["repository_root"]),
        str(value["branch"]),
        datetime.fromisoformat(str(value["starts_at"])),
        datetime.fromisoformat(str(value["expires_at"])),
        _strings(value, "allowed_operations"),
        _strings(value, "allowed_paths"),
        _strings(value, "allowed_source_scopes"),
        str(value["provider"]),
        str(value["model"]),
        str(value["disclosure_policy"]),
        _strings(value, "allowed_categories"),
        _strings(value, "credential_mechanisms"),
        str(value["security_domain"]),
        str(value["classification_scheme"]),
        str(value["classification_level"]),
        int(value["max_requests_per_day"]),
        int(value["max_successes_per_day"]),
        int(value["max_retries_per_day"]),
        float(value["max_daily_spend_aud"]),
        float(value["max_monthly_spend_aud"]),
        int(value["max_output_tokens"]),
        str(value["kill_switch_id"]),
    )


def _strings(value: dict[str, Any], key: str) -> tuple[str, ...]:
    raw = value[key]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(raw)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        raise DelegationError("delegated timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _is_within(path: Path, root: Path) -> bool:
    if not path.is_absolute() or not root.is_absolute():
        return False
    try:
        normalized_path = Path(os.path.abspath(path))
        normalized_root = Path(os.path.abspath(root))
        normalized_path.relative_to(normalized_root)
    except ValueError:
        return False
    return True


def _has_symlink_component(path: Path, repository_root: Path) -> bool:
    if not _is_within(path, repository_root):
        return True
    normalized_path = Path(os.path.abspath(path))
    normalized_root = Path(os.path.abspath(repository_root))
    current = normalized_root
    if current.is_symlink():
        return True
    for part in normalized_path.relative_to(normalized_root).parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _default_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    state = Path(base) if base else Path.home() / ".local" / "state"
    return state / "edn-intelligence-core" / "delegated-authority"
