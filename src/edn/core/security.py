"""Immutable security-context contracts for Intelligence Core."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Self

SCHEMA_VERSION = "1.0.0"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def validate_identifier(value: str, field_name: str) -> str:
    """Validate a durable opaque identifier without rewriting its identity."""
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} is not a valid durable identifier")
    if "::" in value or value.endswith((".", ":")):
        raise ValueError(f"{field_name} is not a valid durable identifier")
    return value


def _optional_identifier(value: str | None, field_name: str) -> str | None:
    return None if value is None else validate_identifier(value, field_name)


def _stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class SecurityDomain:
    """A durable security boundary; label and ownership are descriptive metadata."""

    domain_id: str
    label: str = field(compare=False)
    tenant_id: str | None = None
    owner_id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        validate_identifier(self.domain_id, "domain_id")
        if not self.label.strip():
            raise ValueError("label must not be blank")
        _optional_identifier(self.tenant_id, "tenant_id")
        _optional_identifier(self.owner_id, "owner_id")

    @classmethod
    def scoped(
        cls,
        namespace: str,
        stable_id: str,
        *,
        label: str,
        tenant_id: str,
        owner_id: str | None = None,
    ) -> Self:
        """Create a non-enumerated scoped identity such as CLIENT:stable-id."""
        validate_identifier(namespace, "namespace")
        validate_identifier(stable_id, "stable_id")
        return cls(
            domain_id=f"{namespace}:{stable_id}",
            label=label,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "label": self.label,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(
            domain_id=str(value["domain_id"]),
            label=str(value["label"]),
            tenant_id=_as_optional_str(value.get("tenant_id")),
            owner_id=_as_optional_str(value.get("owner_id")),
        )


@dataclass(frozen=True, slots=True)
class Purpose:
    """An explicit permitted use, distinct from the requested operation."""

    purpose_id: str
    description: str = field(compare=False)

    def __post_init__(self) -> None:
        validate_identifier(self.purpose_id, "purpose_id")
        if not self.description.strip():
            raise ValueError("description must not be blank")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": SCHEMA_VERSION,
            "purpose_id": self.purpose_id,
            "description": self.description,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        return cls(str(value["purpose_id"]), str(value["description"]))


@dataclass(frozen=True, slots=True)
class Classification:
    """A tenant-configurable classification identity, not a global enum."""

    scheme_id: str
    level_id: str
    display_name: str = field(compare=False)
    rank: int | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        validate_identifier(self.scheme_id, "scheme_id")
        validate_identifier(self.level_id, "level_id")
        if not self.display_name.strip():
            raise ValueError("display_name must not be blank")
        if self.rank is not None and self.rank < 0:
            raise ValueError("rank must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "scheme_id": self.scheme_id,
            "level_id": self.level_id,
            "display_name": self.display_name,
            "rank": self.rank,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        rank = value.get("rank")
        return cls(
            scheme_id=str(value["scheme_id"]),
            level_id=str(value["level_id"]),
            display_name=str(value["display_name"]),
            rank=None if rank is None else int(rank),
        )


@dataclass(frozen=True, slots=True)
class PrincipalContext:
    """Authenticated actor context supplied by a future authentication layer."""

    principal_id: str
    tenant_id: str
    active_domains: frozenset[SecurityDomain]
    authenticated: bool
    principal_kind: str = "person"
    delegated_by: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.principal_id, "principal_id")
        validate_identifier(self.tenant_id, "tenant_id")
        validate_identifier(self.principal_kind, "principal_kind")
        _optional_identifier(self.delegated_by, "delegated_by")
        if not self.authenticated:
            raise ValueError("principal context must be authenticated")
        if not self.active_domains:
            raise ValueError("active_domains must not be empty")
        for domain in self.active_domains:
            if domain.tenant_id not in (None, self.tenant_id):
                raise ValueError("active domain belongs to another tenant")
        if self.delegated_by == self.principal_id:
            raise ValueError("principal cannot delegate to itself")

    def allows_domain(self, domain: SecurityDomain) -> bool:
        """Return exact durable-domain eligibility; no hierarchy is implied."""
        if domain.tenant_id not in (None, self.tenant_id):
            return False
        return domain in self.active_domains

    def to_dict(self) -> dict[str, Any]:
        domains = sorted(
            (domain.to_dict() for domain in self.active_domains),
            key=lambda item: str(item["domain_id"]),
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "active_domains": domains,
            "authenticated": self.authenticated,
            "principal_kind": self.principal_kind,
            "delegated_by": self.delegated_by,
        }

    def to_json(self) -> str:
        return _stable_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        _require_schema(value)
        domains = value.get("active_domains")
        if not isinstance(domains, list):
            raise ValueError("active_domains must be a list")
        return cls(
            principal_id=str(value["principal_id"]),
            tenant_id=str(value["tenant_id"]),
            active_domains=frozenset(
                SecurityDomain.from_dict(item) for item in domains
            ),
            authenticated=value.get("authenticated") is True,
            principal_kind=str(value.get("principal_kind", "person")),
            delegated_by=_as_optional_str(value.get("delegated_by")),
        )


def _require_schema(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or missing schema_version")


def _as_optional_str(value: object) -> str | None:
    return None if value is None else str(value)
