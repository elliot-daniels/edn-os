"""Content-free source, record, and evidence reference contracts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import parse_qsl, urlsplit

from edn.core.security import (
    SCHEMA_VERSION,
    Classification,
    PrincipalContext,
    SecurityDomain,
    validate_identifier,
)

_SECRET_QUERY_KEYS = frozenset(
    {"token", "access_token", "refresh_token", "password", "secret", "signature"}
)


def _validate_uri(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError(f"{field_name} is not a valid reference URI")
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain credentials")
    keys = {
        key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    }
    if keys & _SECRET_QUERY_KEYS:
        raise ValueError(f"{field_name} must not contain secret query parameters")


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Reference to one configured source instance without credentials or payload."""

    source_id: str
    connector_id: str
    source_instance_id: str
    display_name: str

    def __post_init__(self) -> None:
        validate_identifier(self.source_id, "source_id")
        validate_identifier(self.connector_id, "connector_id")
        validate_identifier(self.source_instance_id, "source_instance_id")
        if not self.display_name.strip():
            raise ValueError("display_name must not be blank")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_id": self.source_id,
            "connector_id": self.connector_id,
            "source_instance_id": self.source_instance_id,
            "display_name": self.display_name,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            source_id=str(value["source_id"]),
            connector_id=str(value["connector_id"]),
            source_instance_id=str(value["source_instance_id"]),
            display_name=str(value["display_name"]),
        )


@dataclass(frozen=True, slots=True)
class UniversalRecordRef:
    """Durable content-free reference to one record owned by a source."""

    source: SourceRef
    source_record_key: str
    security_domain: SecurityDomain
    classification: Classification
    record_type: str
    source_uri: str | None = None
    source_version: str | None = None

    def __post_init__(self) -> None:
        if not self.source_record_key or any(
            character in self.source_record_key for character in "\r\n"
        ):
            raise ValueError("source_record_key must not be blank or multiline")
        validate_identifier(self.record_type, "record_type")
        _validate_uri(self.source_uri, "source_uri")
        if self.source_version is not None and not self.source_version.strip():
            raise ValueError("source_version must not be blank")

    @property
    def durable_id(self) -> tuple[str, str]:
        """Identity preserves the source key exactly; it is not case-normalized."""
        return (self.source.source_id, self.source_record_key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": self.source.to_dict(),
            "source_record_key": self.source_record_key,
            "security_domain": self.security_domain.to_dict(),
            "classification": self.classification.to_dict(),
            "record_type": self.record_type,
            "source_uri": self.source_uri,
            "source_version": self.source_version,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            source=SourceRef.from_dict(_dict(value["source"])),
            source_record_key=str(value["source_record_key"]),
            security_domain=SecurityDomain.from_dict(_dict(value["security_domain"])),
            classification=Classification.from_dict(_dict(value["classification"])),
            record_type=str(value["record_type"]),
            source_uri=_optional_str(value.get("source_uri")),
            source_version=_optional_str(value.get("source_version")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Bounded evidence pointer; never contains full source content."""

    evidence_id: str
    record: UniversalRecordRef
    locator: str | None = None
    transformation_id: str | None = None
    transformation_version: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.evidence_id, "evidence_id")
        if self.locator is not None and (
            not self.locator.strip() or len(self.locator) > 512
        ):
            raise ValueError("locator must be bounded and nonblank")
        if self.transformation_id is not None:
            validate_identifier(self.transformation_id, "transformation_id")
            if not self.transformation_version:
                raise ValueError("transformation_version is required")
        elif self.transformation_version is not None:
            raise ValueError("transformation_id is required")
        if self.content_hash is not None and not _is_sha256(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 value")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "evidence_id": self.evidence_id,
            "record": self.record.to_dict(),
            "locator": self.locator,
            "transformation_id": self.transformation_id,
            "transformation_version": self.transformation_version,
            "content_hash": self.content_hash,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            evidence_id=str(value["evidence_id"]),
            record=UniversalRecordRef.from_dict(_dict(value["record"])),
            locator=_optional_str(value.get("locator")),
            transformation_id=_optional_str(value.get("transformation_id")),
            transformation_version=_optional_str(value.get("transformation_version")),
            content_hash=_optional_str(value.get("content_hash")),
        )


def is_evidence_eligible(
    context: PrincipalContext | None,
    evidence: EvidenceRef,
) -> bool:
    """Fail closed unless an authenticated context explicitly allows the domain."""
    return context is not None and context.allows_domain(
        evidence.record.security_domain
    )


def filter_eligible_evidence(
    context: PrincipalContext | None,
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    """Filter before citation, ranking, or aggregate calculation."""
    return tuple(item for item in evidence if is_evidence_eligible(context, item))


def count_eligible_evidence(
    context: PrincipalContext | None,
    evidence: Iterable[EvidenceRef],
) -> int:
    """Count only accessible evidence to prevent aggregate side channels."""
    return sum(is_evidence_eligible(context, item) for item in evidence)


def _require_schema(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")


def _dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("serialized nested model must be an object")
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
