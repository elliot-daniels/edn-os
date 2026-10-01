"""Protected owner-review handoff for validated PA-009 typed results."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from edn.core import Classification
from edn.intelligence.model_boundary import (
    ModelResponse,
    ModelStatement,
    ModelStatementKind,
)
from edn.intelligence.provider_preflight_store import canonical_json

SCHEMA_VERSION = "1.0.0"
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
DEFAULT_RETENTION = timedelta(days=30)
MAX_RESULT_BYTES = 64 * 1024
MAX_STATEMENTS = 10
MAX_STATEMENT_TEXT_CHARS = 2_000
MAX_UNCERTAINTY_CHARS = 1_000
MAX_EVIDENCE_REFERENCES = 25
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class ProviderResultStoreError(RuntimeError):
    """A validated provider result cannot be persisted or reviewed safely."""


@dataclass(frozen=True, slots=True)
class ValidatedProviderResult:
    """Sanitised typed model output; never a verified factual record."""

    request_id: str
    preflight_hash: str
    provider_id: str
    model: str
    disclosure_policy: str
    security_domain: str
    classification: Classification
    created_at: datetime
    expires_at: datetime
    schema_validation: str
    citation_validation: str
    statements: tuple[ModelStatement, ...]

    def __post_init__(self) -> None:
        identifiers = (
            self.request_id,
            self.provider_id,
            self.model,
            self.disclosure_policy,
            self.security_domain,
        )
        if not all(_IDENTIFIER.fullmatch(value) for value in identifiers):
            raise ValueError("provider result identifier is invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.preflight_hash):
            raise ValueError("provider result preflight hash is invalid")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("provider result timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("provider result expiry must follow creation")
        if self.schema_validation != "passed" or self.citation_validation != "passed":
            raise ValueError("only fully validated provider results may be retained")
        if not 1 <= len(self.statements) <= MAX_STATEMENTS:
            raise ValueError("provider result statement count is invalid")
        for statement in self.statements:
            _validate_statement(statement)

    def grouped_statements(
        self,
    ) -> dict[ModelStatementKind, tuple[ModelStatement, ...]]:
        """Return exact typed statements grouped for owner review."""
        return {
            kind: tuple(item for item in self.statements if item.kind is kind)
            for kind in ModelStatementKind
        }


class OwnerReviewResultStore:
    """Owner-only result storage with no provider or execution authority."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        retention: timedelta = DEFAULT_RETENTION,
    ) -> None:
        if retention <= timedelta(0) or retention > DEFAULT_RETENTION:
            raise ValueError("provider result retention must be within 30 days")
        self.root = root or _default_root()
        self.retention = retention

    def persist_validated(
        self,
        response: ModelResponse,
        *,
        preflight_hash: str,
        model: str,
        disclosure_policy: str,
        security_domain: str,
        classification: Classification,
        validated_evidence_ids: frozenset[str],
        created_at: datetime | None = None,
    ) -> ValidatedProviderResult:
        """Persist only an already parsed, semantically and citation-valid result."""
        if response.provider_id != "openai.api":
            raise ProviderResultStoreError("provider result identity is invalid")
        if set(response.disclosed_evidence_ids) != validated_evidence_ids:
            raise ProviderResultStoreError(
                "provider result evidence binding is invalid"
            )
        if any(
            not set(statement.disclosed_evidence_ids) <= validated_evidence_ids
            for statement in response.statements
        ):
            raise ProviderResultStoreError(
                "provider result citation binding is invalid"
            )
        timestamp = created_at or datetime.now(UTC)
        try:
            result = ValidatedProviderResult(
                response.request_id,
                preflight_hash,
                response.provider_id,
                model,
                disclosure_policy,
                security_domain,
                classification,
                timestamp,
                timestamp + self.retention,
                "passed",
                "passed",
                response.statements,
            )
        except ValueError as exc:
            raise ProviderResultStoreError(
                "provider result sanitisation failed"
            ) from exc
        self._persist(result)
        return result

    def load(
        self, request_id: str, *, now: datetime | None = None
    ) -> ValidatedProviderResult:
        """Read one exact result; this API grants no approval or dispatch capability."""
        self._secure_directory(create=False)
        path = self._path(request_id)
        result = self._read(path)
        if result.request_id != request_id:
            raise ProviderResultStoreError("provider result request mismatch")
        if result.expires_at <= (now or datetime.now(UTC)):
            self._unlink(path)
            self._fsync_directory()
            raise ProviderResultStoreError("provider result expired")
        return result

    def remove_expired(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Remove decoded expired results; corrupt files remain fail closed."""
        self._secure_directory(create=False)
        current = now or datetime.now(UTC)
        removed: list[str] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                result = self._read(path)
            except ProviderResultStoreError:
                continue
            if result.expires_at <= current:
                self._unlink(path)
                removed.append(result.request_id)
        if removed:
            self._fsync_directory()
        return tuple(removed)

    def _persist(self, result: ValidatedProviderResult) -> None:
        self._secure_directory(create=True)
        destination = self._path(result.request_id)
        if destination.exists() or destination.is_symlink():
            raise ProviderResultStoreError("provider result already exists")
        document = _document(result)
        payload = canonical_json(document)
        if len(payload) > MAX_RESULT_BYTES:
            raise ProviderResultStoreError("provider result exceeds size limit")
        temporary = self.root / (
            f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, FILE_MODE)
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(descriptor, remaining)
                if written < 1:
                    raise ProviderResultStoreError("provider result write failed")
                remaining = remaining[written:]
            os.fsync(descriptor)
            os.fchmod(descriptor, FILE_MODE)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError as exc:
            raise ProviderResultStoreError("provider result already exists") from exc
        finally:
            self._unlink(temporary)
        self._validate_file(destination)
        self._fsync_directory()

    def _read(self, path: Path) -> ValidatedProviderResult:
        descriptor = self._open_read(path)
        try:
            data = os.read(descriptor, MAX_RESULT_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(data) > MAX_RESULT_BYTES:
            raise ProviderResultStoreError("provider result exceeds size limit")
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderResultStoreError("provider result is invalid") from exc
        if not isinstance(value, dict) or canonical_json(value) != data:
            raise ProviderResultStoreError("provider result is not canonical")
        integrity_hash = value.get("integrity_hash")
        binding = dict(value)
        binding.pop("integrity_hash", None)
        if (
            not isinstance(integrity_hash, str)
            or hashlib.sha256(canonical_json(binding)).hexdigest() != integrity_hash
        ):
            raise ProviderResultStoreError("provider result integrity check failed")
        try:
            return _result(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderResultStoreError(
                "provider result fields are invalid"
            ) from exc

    def _open_read(self, path: Path) -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ProviderResultStoreError("provider result is unavailable") from exc
        try:
            self._validate_stat(os.fstat(descriptor), FILE_MODE, regular=True)
        except ProviderResultStoreError:
            os.close(descriptor)
            raise
        return descriptor

    def _secure_directory(self, *, create: bool) -> None:
        if create:
            self.root.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        try:
            value = self.root.stat(follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ProviderResultStoreError(
                "provider result directory is missing"
            ) from exc
        self._validate_stat(value, DIRECTORY_MODE, regular=False)

    @staticmethod
    def _validate_stat(value: os.stat_result, mode: int, *, regular: bool) -> None:
        expected = stat.S_ISREG if regular else stat.S_ISDIR
        if not expected(value.st_mode):
            raise ProviderResultStoreError("provider result path type is unsafe")
        if value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) != mode:
            raise ProviderResultStoreError(
                "provider result ownership or mode is unsafe"
            )

    def _validate_file(self, path: Path) -> None:
        self._validate_stat(path.stat(follow_symlinks=False), FILE_MODE, regular=True)

    def _path(self, request_id: str) -> Path:
        if not _IDENTIFIER.fullmatch(request_id):
            raise ProviderResultStoreError("provider result request ID is invalid")
        return self.root / f"{hashlib.sha256(request_id.encode()).hexdigest()}.json"

    def _fsync_directory(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.root, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _unlink(path: Path) -> None:
        with suppress(FileNotFoundError):
            path.unlink()


def _document(result: ValidatedProviderResult) -> dict[str, object]:
    binding: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": result.request_id,
        "preflight_hash": result.preflight_hash,
        "provider": result.provider_id,
        "model": result.model,
        "disclosure_policy": result.disclosure_policy,
        "security_domain": result.security_domain,
        "classification": result.classification.to_dict(),
        "created_at": _timestamp(result.created_at),
        "expires_at": _timestamp(result.expires_at),
        "schema_validation": result.schema_validation,
        "citation_validation": result.citation_validation,
        "statements": [_statement(item) for item in result.statements],
    }
    return {
        **binding,
        "integrity_hash": hashlib.sha256(canonical_json(binding)).hexdigest(),
    }


def _result(value: dict[str, Any]) -> ValidatedProviderResult:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("provider result schema is unsupported")
    expected = {
        "schema_version", "request_id", "preflight_hash", "provider", "model",
        "disclosure_policy", "security_domain", "classification", "created_at",
        "expires_at", "schema_validation", "citation_validation", "statements",
        "integrity_hash",
    }
    if set(value) != expected or not isinstance(value["statements"], list):
        raise ValueError("provider result schema is invalid")
    string_fields = (
        "request_id", "preflight_hash", "provider", "model",
        "disclosure_policy", "security_domain", "created_at", "expires_at",
        "schema_validation", "citation_validation", "integrity_hash",
    )
    if not all(isinstance(value[field], str) for field in string_fields):
        raise ValueError("provider result field type is invalid")
    return ValidatedProviderResult(
        str(value["request_id"]),
        str(value["preflight_hash"]),
        str(value["provider"]),
        str(value["model"]),
        str(value["disclosure_policy"]),
        str(value["security_domain"]),
        Classification.from_dict(_object(value["classification"])),
        _datetime(value["created_at"]),
        _datetime(value["expires_at"]),
        str(value["schema_validation"]),
        str(value["citation_validation"]),
        tuple(_model_statement(_object(item)) for item in value["statements"]),
    )


def _statement(value: ModelStatement) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "text": value.text,
        "disclosed_evidence_ids": list(value.disclosed_evidence_ids),
        "uncertainty": value.uncertainty,
        "proposal_only": value.proposal_only,
    }


def _model_statement(value: dict[str, Any]) -> ModelStatement:
    expected = {
        "kind", "text", "disclosed_evidence_ids", "uncertainty", "proposal_only"
    }
    if (
        set(value) != expected
        or not isinstance(value["kind"], str)
        or not isinstance(value["text"], str)
        or not isinstance(value["disclosed_evidence_ids"], list)
        or not all(
            isinstance(item, str) for item in value["disclosed_evidence_ids"]
        )
        or (
            value["uncertainty"] is not None
            and not isinstance(value["uncertainty"], str)
        )
        or not isinstance(value["proposal_only"], bool)
    ):
        raise ValueError("provider result statement schema is invalid")
    return ModelStatement(
        ModelStatementKind(str(value["kind"])),
        value["text"],
        tuple(value["disclosed_evidence_ids"]),
        value["uncertainty"],
        "openai.api",
        value["proposal_only"],
    )


def _validate_statement(value: ModelStatement) -> None:
    if not 1 <= len(value.text) <= MAX_STATEMENT_TEXT_CHARS:
        raise ValueError("provider result statement text is invalid")
    if _has_unsafe_control(value.text):
        raise ValueError("provider result statement text contains unsafe controls")
    if value.uncertainty is not None and (
        len(value.uncertainty) > MAX_UNCERTAINTY_CHARS
        or _has_unsafe_control(value.uncertainty)
    ):
        raise ValueError("provider result uncertainty is invalid")
    if len(value.disclosed_evidence_ids) > MAX_EVIDENCE_REFERENCES or not all(
        _IDENTIFIER.fullmatch(item) for item in value.disclosed_evidence_ids
    ):
        raise ValueError("provider result evidence reference is invalid")
    if value.kind is ModelStatementKind.PROPOSED_ACTION and not value.proposal_only:
        raise ValueError("provider result action must remain proposal-only")
    if value.kind is not ModelStatementKind.PROPOSED_ACTION and value.proposal_only:
        raise ValueError("provider result non-action cannot become proposal-only")


def _has_unsafe_control(value: str) -> bool:
    return any(
        ord(character) < 32 and character not in {"\n", "\t"}
        for character in value
    )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("provider result object is invalid")
    return value


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider result timestamp is naive")
    return parsed


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _default_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    state = Path(base) if base else Path.home() / ".local" / "state"
    return state / "edn-intelligence-core" / "provider-results"
