"""Conservative current-mail models for synthetic-only Outlook development."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from edn.core import Classification, SecurityDomain


class MailWindow(StrEnum):
    LAST_24_HOURS = "last-24-hours"
    LAST_7_DAYS = "last-7-days"
    LAST_30_DAYS = "last-30-days"

    def bounds(self, now: datetime) -> tuple[datetime, datetime]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        days = {
            self.LAST_24_HOURS: 1,
            self.LAST_7_DAYS: 7,
            self.LAST_30_DAYS: 30,
        }[self]
        return now - timedelta(days=days), now


class MailScopeMode(StrEnum):
    DEDICATED_EDN = "dedicated-edn"
    CATEGORY_REQUIRED = "category-required"


@dataclass(frozen=True, slots=True)
class OutlookConfig:
    tenant_id: str
    account_id: str
    mailbox_id: str
    folder_ids: tuple[str, ...]
    security_domain: SecurityDomain
    classification: Classification
    scope_mode: MailScopeMode
    required_category: str | None = None
    include_body: bool = False
    include_attachments: bool = False

    def __post_init__(self) -> None:
        identities = (
            self.tenant_id,
            self.account_id,
            self.mailbox_id,
            *self.folder_ids,
        )
        if any(
            not value.strip() or "\n" in value or "\r" in value for value in identities
        ):
            raise ValueError("Outlook identity and folder values must be nonblank")
        if not self.folder_ids:
            raise ValueError("at least one exact Outlook folder is required")
        if self.include_body or self.include_attachments:
            raise ValueError("PA-003 excludes mail bodies and attachments")
        if self.scope_mode is MailScopeMode.CATEGORY_REQUIRED:
            if not self.required_category or not self.required_category.strip():
                raise ValueError("category-required mode needs an exact category")
        elif self.required_category is not None:
            raise ValueError("dedicated-mailbox mode does not accept a category")


@dataclass(frozen=True, slots=True)
class OutlookMessage:
    message_id: str
    mailbox_id: str
    folder_id: str
    subject: str
    sender: str
    recipients: tuple[str, ...]
    received_at: datetime
    last_modified_at: datetime
    importance: str
    is_read: bool
    categories: tuple[str, ...]
    web_url: str | None
    security_domain: SecurityDomain
    classification: Classification

    def __post_init__(self) -> None:
        if not self.message_id or not self.folder_id or not self.subject.strip():
            raise ValueError("mail identity, folder and subject must be nonblank")
        if self.received_at.tzinfo is None or self.last_modified_at.tzinfo is None:
            raise ValueError("mail timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OutlookRetrievalResult:
    pre_filter_count: int
    messages: tuple[OutlookMessage, ...]

    @property
    def admitted_count(self) -> int:
        return len(self.messages)

    @property
    def rejected_count(self) -> int:
        return self.pre_filter_count - self.admitted_count
