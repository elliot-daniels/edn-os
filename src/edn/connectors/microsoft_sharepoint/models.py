"""Bounded Business OS SharePoint record models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from edn.core import Classification, SecurityDomain


@dataclass(frozen=True, slots=True)
class SharePointConfig:
    tenant_id: str
    site_id: str
    list_id: str
    list_name: str
    allowed_fields: tuple[str, ...]
    security_field: str
    expected_security_value: str
    security_domain: SecurityDomain
    classification: Classification
    freshness_days: int = 30

    def __post_init__(self) -> None:
        text = (
            self.tenant_id,
            self.site_id,
            self.list_id,
            self.list_name,
            self.security_field,
            self.expected_security_value,
            *self.allowed_fields,
        )
        if any(not value.strip() or "\n" in value or "\r" in value for value in text):
            raise ValueError("SharePoint configuration values must be nonblank")
        if not self.allowed_fields or len(set(self.allowed_fields)) != len(
            self.allowed_fields
        ):
            raise ValueError("allowed_fields must be nonempty and unique")
        if self.security_field not in self.allowed_fields:
            raise ValueError("security_field must be explicitly allowed")
        if not 1 <= self.freshness_days <= 365:
            raise ValueError("freshness_days must be between 1 and 365")


@dataclass(frozen=True, slots=True)
class SharePointRecord:
    item_id: str
    title: str
    fields: tuple[tuple[str, str], ...]
    modified_at: datetime
    retrieved_at: datetime
    security_value: str
    web_url: str | None
    etag: str | None
    security_domain: SecurityDomain
    classification: Classification

    def __post_init__(self) -> None:
        if not self.item_id.strip() or not self.title.strip():
            raise ValueError("SharePoint item identity and title must be nonblank")
        if self.modified_at.tzinfo is None or self.retrieved_at.tzinfo is None:
            raise ValueError("SharePoint timestamps must be timezone-aware")
        if len({name for name, _ in self.fields}) != len(self.fields):
            raise ValueError("SharePoint field names must be unique")

    def is_fresh(self, *, freshness_days: int) -> bool:
        return self.modified_at >= self.retrieved_at - timedelta(days=freshness_days)


@dataclass(frozen=True, slots=True)
class SharePointRetrievalResult:
    pre_filter_count: int
    records: tuple[SharePointRecord, ...]

    @property
    def admitted_count(self) -> int:
        return len(self.records)

    @property
    def rejected_count(self) -> int:
        return self.pre_filter_count - self.admitted_count
