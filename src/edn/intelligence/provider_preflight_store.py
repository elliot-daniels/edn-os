"""Protected short-lived storage for exact provider-visible PA-009 projections."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from edn.core import Classification
from edn.intelligence.model_boundary import (
    DisclosureProjection,
    ModelRequest,
    ProjectedEvidence,
)
from edn.intelligence.models import FreshnessState

SCHEMA_VERSION = "1.0.0"
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
MAX_ENVELOPE_BYTES = 64 * 1024
RETRYABLE_INITIAL_FAILURE_CODES = frozenset(
    {"timeout", "quota_rate_limit", "provider_unavailable", "network_failure"}
)


class ProtectedPreflightError(RuntimeError):
    """A protected envelope cannot be safely stored, loaded, or consumed."""


@dataclass(frozen=True, slots=True)
class ProtectedProjectionEnvelope:
    request: ModelRequest
    preflight_hash: str
    provider_id: str
    model: str
    disclosure_policy: str
    security_domain: str
    classification_ceiling: str
    projected_categories: tuple[str, ...]
    evidence_count: int
    created_at: datetime
    expires_at: datetime
    dispatch_attempts: int = 0
    initial_failure_code: str | None = None
    initial_failure_retryable: bool = False

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("protected preflight timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("protected preflight expiry must follow creation")
        if self.dispatch_attempts < 0 or self.dispatch_attempts > 2:
            raise ValueError("protected preflight dispatch attempts are invalid")
        if self.dispatch_attempts == 0 and (
            self.initial_failure_code is not None or self.initial_failure_retryable
        ):
            raise ValueError("initial failure metadata requires a retry attempt")
        if self.dispatch_attempts > 0 and (
            self.initial_failure_code not in RETRYABLE_INITIAL_FAILURE_CODES
            or not self.initial_failure_retryable
        ):
            raise ValueError(
                "retry attempt requires retryable initial failure metadata"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "request": _request_dict(self.request),
            "preflight_hash": self.preflight_hash,
            "provider_id": self.provider_id,
            "model": self.model,
            "disclosure_policy": self.disclosure_policy,
            "security_domain": self.security_domain,
            "classification_ceiling": self.classification_ceiling,
            "projected_categories": list(self.projected_categories),
            "evidence_count": self.evidence_count,
            "created_at": _timestamp(self.created_at),
            "expires_at": _timestamp(self.expires_at),
            "dispatch_attempts": self.dispatch_attempts,
            "initial_failure_code": self.initial_failure_code,
            "initial_failure_retryable": self.initial_failure_retryable,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ProtectedPreflightError("unsupported protected preflight schema")
        return cls(
            _request(_object(value.get("request"))),
            str(value["preflight_hash"]),
            str(value["provider_id"]),
            str(value["model"]),
            str(value["disclosure_policy"]),
            str(value["security_domain"]),
            str(value["classification_ceiling"]),
            tuple(str(item) for item in _list(value.get("projected_categories"))),
            int(value["evidence_count"]),
            _datetime(value["created_at"]),
            _datetime(value["expires_at"]),
            int(value.get("dispatch_attempts", 0)),
            (
                None
                if value.get("initial_failure_code") is None
                else str(value["initial_failure_code"])
            ),
            value.get("initial_failure_retryable") is True,
        )


def canonical_json(value: object) -> bytes:
    """Return the single canonical serialization used for disk and hashing."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


class ProtectedPreflightStore:
    """Owner-only active/claimed envelope store with atomic single-use claims."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _default_root()

    def persist(self, envelope: ProtectedProjectionEnvelope) -> Path:
        self._secure_directory(create=True)
        active = self._path(envelope.request.request_id, claimed=False)
        claimed = self._path(envelope.request.request_id, claimed=True)
        if active.exists() or claimed.exists():
            raise ProtectedPreflightError("protected preflight already exists")
        payload = canonical_json(envelope.to_dict())
        if len(payload) > MAX_ENVELOPE_BYTES:
            raise ProtectedPreflightError("protected preflight exceeds size limit")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(active, flags, FILE_MODE)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as destination:
                destination.write(payload)
                destination.flush()
                os.fsync(destination.fileno())
            os.fchmod(descriptor, FILE_MODE)
        finally:
            os.close(descriptor)
        self._validate_file(active)
        return active

    def load(
        self, request_id: str, *, now: datetime | None = None
    ) -> ProtectedProjectionEnvelope:
        self._secure_directory(create=False)
        envelope = self._read(self._path(request_id, claimed=False))
        if envelope.request.request_id != request_id:
            raise ProtectedPreflightError("protected preflight request mismatch")
        if envelope.expires_at <= (now or datetime.now(UTC)):
            self.cancel(request_id)
            raise ProtectedPreflightError("protected preflight expired")
        return envelope

    def claim(
        self, request_id: str, *, now: datetime | None = None
    ) -> ProtectedProjectionEnvelope:
        self._secure_directory(create=False)
        active = self._path(request_id, claimed=False)
        claimed = self._path(request_id, claimed=True)
        if claimed.exists():
            raise ProtectedPreflightError("protected preflight is already claimed")
        try:
            os.replace(active, claimed)
        except FileNotFoundError as exc:
            raise ProtectedPreflightError("protected preflight is missing") from exc
        envelope = self._read(claimed)
        if envelope.request.request_id != request_id:
            self.destroy_claim(request_id)
            raise ProtectedPreflightError("protected preflight request mismatch")
        if envelope.expires_at <= (now or datetime.now(UTC)):
            self.destroy_claim(request_id)
            raise ProtectedPreflightError("protected preflight expired")
        if envelope.dispatch_attempts >= 2:
            self.destroy_claim(request_id)
            raise ProtectedPreflightError("protected preflight retry limit reached")
        return envelope

    def restore_retry(
        self, envelope: ProtectedProjectionEnvelope, *, failure_code: str
    ) -> None:
        claimed = self._path(envelope.request.request_id, claimed=True)
        active = self._path(envelope.request.request_id, claimed=False)
        self._validate_file(claimed)
        if active.exists():
            raise ProtectedPreflightError("active protected preflight already exists")
        if envelope.dispatch_attempts != 0 or not failure_code:
            raise ProtectedPreflightError("protected preflight retry is invalid")
        updated = replace(
            envelope,
            dispatch_attempts=1,
            initial_failure_code=failure_code,
            initial_failure_retryable=True,
        )
        self._rewrite_claimed(claimed, updated)
        os.replace(claimed, active)

    def destroy_claim(self, request_id: str) -> None:
        self._unlink(self._path(request_id, claimed=True))

    def cancel(self, request_id: str) -> None:
        self._unlink(self._path(request_id, claimed=False))
        self._unlink(self._path(request_id, claimed=True))

    def exists(self, request_id: str) -> bool:
        return self._path(request_id, claimed=False).exists()

    def _rewrite_claimed(
        self, path: Path, envelope: ProtectedProjectionEnvelope
    ) -> None:
        descriptor = self._open_read(path)
        try:
            file_stat = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        temporary = path.with_suffix(".retry.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        output = os.open(temporary, flags, FILE_MODE)
        try:
            data = canonical_json(envelope.to_dict())
            os.write(output, data)
            os.fsync(output)
            os.fchmod(output, FILE_MODE)
        finally:
            os.close(output)
        if path.stat().st_ino != file_stat.st_ino:
            self._unlink(temporary)
            raise ProtectedPreflightError("protected preflight changed during retry")
        os.replace(temporary, path)

    def _read(self, path: Path) -> ProtectedProjectionEnvelope:
        descriptor = self._open_read(path)
        try:
            file_stat = os.fstat(descriptor)
            self._validate_stat(file_stat, FILE_MODE, regular=True)
            data = os.read(descriptor, MAX_ENVELOPE_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(data) > MAX_ENVELOPE_BYTES:
            raise ProtectedPreflightError("protected preflight exceeds size limit")
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtectedPreflightError("protected preflight is invalid") from exc
        if not isinstance(value, dict) or canonical_json(value) != data:
            raise ProtectedPreflightError("protected preflight is not canonical")
        try:
            return ProtectedProjectionEnvelope.from_dict(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtectedPreflightError(
                "protected preflight fields are invalid"
            ) from exc

    def _open_read(self, path: Path) -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(path, flags)
        except (FileNotFoundError, OSError) as exc:
            raise ProtectedPreflightError("protected preflight is unavailable") from exc

    def _secure_directory(self, *, create: bool) -> None:
        if create:
            self.root.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        try:
            directory_stat = self.root.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ProtectedPreflightError(
                "protected preflight directory is missing"
            ) from exc
        self._validate_stat(directory_stat, DIRECTORY_MODE, regular=False)

    @staticmethod
    def _validate_stat(value: os.stat_result, mode: int, *, regular: bool) -> None:
        expected_type = stat.S_ISREG if regular else stat.S_ISDIR
        if not expected_type(value.st_mode):
            raise ProtectedPreflightError("protected preflight path type is unsafe")
        if value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != mode:
            raise ProtectedPreflightError(
                "protected preflight ownership or mode is unsafe"
            )

    def _validate_file(self, path: Path) -> None:
        self._validate_stat(path.stat(follow_symlinks=False), FILE_MODE, regular=True)

    def _path(self, request_id: str, *, claimed: bool) -> Path:
        name = hashlib.sha256(request_id.encode()).hexdigest()
        return self.root / f"{name}{'.claimed' if claimed else '.json'}"

    @staticmethod
    def _unlink(path: Path) -> None:
        with suppress(FileNotFoundError):
            path.unlink()


def _default_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    state = Path(base) if base else Path.home() / ".local" / "state"
    return state / "edn-intelligence-core" / "provider-preflights"


def _request_dict(request: ModelRequest) -> dict[str, object]:
    return {
        "request_id": request.request_id,
        "purpose": request.purpose,
        "security_domain": request.security_domain,
        "projection": {
            "request_id": request.projection.request_id,
            "total_chars": request.projection.total_chars,
            "redactions": list(request.projection.redactions),
            "items": [_item_dict(item) for item in request.projection.items],
        },
        "classification": request.classification.to_dict(),
        "max_output_items": request.max_output_items,
        "synthetic_fixture": request.synthetic_fixture,
    }


def _item_dict(item: ProjectedEvidence) -> dict[str, object]:
    return {
        "disclosure_id": item.disclosure_id,
        "source_family": item.source_family,
        "title": item.title,
        "excerpt": item.excerpt,
        "freshness": item.freshness.value,
        "provenance_digest": item.provenance_digest,
        "source_timestamp": (
            None if item.source_timestamp is None else _timestamp(item.source_timestamp)
        ),
        "field_category": item.field_category,
        "provider_approved": item.provider_approved,
    }


def _request(value: dict[str, Any]) -> ModelRequest:
    projection = _object(value.get("projection"))
    return ModelRequest(
        str(value["request_id"]),
        str(value["purpose"]),
        "protected-owner",
        str(value["security_domain"]),
        tuple(
            str(_object(item)["disclosure_id"])
            for item in _list(projection.get("items"))
        ),
        DisclosureProjection(
            str(projection["request_id"]),
            tuple(_item(_object(item)) for item in _list(projection.get("items"))),
            int(projection["total_chars"]),
            tuple(str(item) for item in _list(projection.get("redactions"))),
        ),
        Classification.from_dict(_object(value.get("classification"))),
        "model.summarize",
        int(value["max_output_items"]),
        value.get("synthetic_fixture") is True,
    )


def _item(value: dict[str, Any]) -> ProjectedEvidence:
    timestamp = value.get("source_timestamp")
    return ProjectedEvidence(
        str(value["disclosure_id"]),
        str(value["source_family"]),
        str(value["title"]),
        str(value["excerpt"]),
        FreshnessState(str(value["freshness"])),
        str(value["provenance_digest"]),
        None if timestamp is None else _datetime(timestamp),
        str(value["field_category"]),
        value.get("provider_approved") is True,
    )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtectedPreflightError("protected preflight object is invalid")
    return value


def _list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ProtectedPreflightError("protected preflight list is invalid")
    return value


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProtectedPreflightError("protected preflight timestamp is naive")
    return parsed


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
