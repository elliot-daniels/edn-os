"""Bounded read-only Outlook mail connector over a supplied client boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from edn.connectors import (
    ConnectorManifest,
    ConnectorRequest,
    SearchResult,
    VerificationResult,
    VerificationStatus,
    require_supported_operation,
)
from edn.connectors.admission import AdmissionDecision, AdmissionOutcome
from edn.connectors.microsoft_outlook.admission import EmailAdmissionPolicy
from edn.connectors.microsoft_outlook.client import GraphOutlookClient
from edn.connectors.microsoft_outlook.models import (
    MailScopeMode,
    MailWindow,
    OutlookConfig,
    OutlookMessage,
    OutlookRetrievalResult,
)
from edn.core import CapabilityManifest, EvidenceRef, SourceRef, UniversalRecordRef

CONNECTOR_ID = "microsoft-outlook"
CONNECTOR_VERSION = "0.1.0"
READ_PERMISSION = "Mail.Read"


class MicrosoftOutlookConnector:
    def __init__(
        self,
        config: OutlookConfig,
        client: GraphOutlookClient,
        *,
        admission_policy: EmailAdmissionPolicy | None = None,
    ) -> None:
        self.config = config
        self.client = client
        if (config.scope_mode is MailScopeMode.ADMISSION_V2) != (
            admission_policy is not None
        ):
            raise ValueError(
                "V2 requires an explicit admission policy; V1 cannot use it"
            )
        if admission_policy is not None and (
            admission_policy.security_domain != config.security_domain
            or admission_policy.classification != config.classification
        ):
            raise ValueError("admission policy does not match connector domain")
        self.admission_policy = admission_policy
        capabilities = tuple(
            CapabilityManifest(
                capability_id,
                "microsoft-graph",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                frozenset({operation}),
                frozenset({READ_PERMISSION}),
                frozenset({config.security_domain.domain_id}),
                "read",
            )
            for capability_id, operation in (
                ("outlook.search", "search"),
                ("outlook.verify", "verify"),
            )
        )
        self._manifest = ConnectorManifest(
            CONNECTOR_ID,
            CONNECTOR_VERSION,
            "Microsoft 365 Outlook Mail",
            "microsoft-graph",
            "Bounded current-mail metadata retrieval; bodies and attachments excluded.",
            "email",
            capabilities,
            frozenset({"search", "verify"}),
            "urn:edn:schema:microsoft-outlook-config:1",
            "1.0.0",
        )

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    @property
    def admission_scope(self) -> tuple[str, ...]:
        return (
            ()
            if self.admission_policy is None
            else (self.admission_policy.authority_id,)
        )

    def search_messages(
        self,
        request: ConnectorRequest,
        *,
        window: MailWindow,
        now: datetime,
        limit: int,
    ) -> OutlookRetrievalResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        if not 1 <= limit <= 25:
            raise ValueError("Outlook retrieval limit must be between 1 and 25")
        start, end = window.bounds(now)
        raw: list[dict[str, Any]] = []
        for folder_id in self.config.folder_ids:
            remaining = limit - len(raw)
            if remaining <= 0:
                break
            raw.extend(
                self.client.messages(
                    self.config.mailbox_id,
                    folder_id,
                    start,
                    end,
                    limit=remaining,
                )
            )
        messages: list[OutlookMessage] = []
        if self.admission_policy is not None:
            return self._admit_batch(raw, start=start, end=end, now=now)
        for item in raw:
            message = self._message(item)
            if message is None or not start <= message.received_at <= end:
                continue
            messages.append(message)
        admitted = tuple(
            sorted(
                messages,
                key=lambda item: (item.received_at, item.message_id),
                reverse=True,
            )
        )
        return OutlookRetrievalResult(len(raw), admitted)

    def _admit_batch(
        self,
        raw: list[dict[str, Any]],
        *,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> OutlookRetrievalResult:
        policy = self.admission_policy
        assert policy is not None
        fingerprints: dict[str, set[str]] = {}
        for item in raw:
            key = str(item.get("id", "unidentified"))
            fingerprints.setdefault(key, set()).add(
                json.dumps(item, sort_keys=True, default=str)
            )
        seen: set[str] = set()
        decisions: list[AdmissionDecision] = []
        messages: list[OutlookMessage] = []
        for item in raw:
            key = str(item.get("id", "unidentified"))
            decision = policy.decide(item, now=now)
            reason = ""
            message = None
            if len(fingerprints[key]) > 1:
                reason = "conflicting_metadata"
            elif key in seen:
                reason = "duplicate_record"
            elif decision.reasons == ("malformed_metadata",):
                reason = "malformed_metadata"
            else:
                try:
                    message = self._message(item)
                    if message is None:
                        reason = "outside_folder_boundary"
                    elif not start <= message.received_at <= end:
                        reason = "outside_time_boundary"
                except (KeyError, TypeError, ValueError):
                    reason = "malformed_metadata"
            seen.add(key)
            if reason:
                decision = AdmissionDecision(
                    key, policy.authority_id, AdmissionOutcome.REJECTED, (reason,)
                )
            decisions.append(decision)
            if decision.outcome is AdmissionOutcome.ADMITTED and message is not None:
                messages.append(message)
        messages.sort(
            key=lambda item: (item.received_at, item.message_id), reverse=True
        )
        reasons = set(policy.coverage(now))
        if not messages:
            reasons.add("no_admissible_evidence")
        return OutlookRetrievalResult(
            len(raw), tuple(messages), tuple(decisions), tuple(sorted(reasons))
        )

    def search(self, request: ConnectorRequest) -> SearchResult:
        result = self.search_messages(
            request,
            window=_window_from_scope(request.scope),
            now=datetime.now(UTC),
            limit=25,
        )
        return SearchResult(
            request.request_id,
            tuple(self.evidence_ref(item) for item in result.messages),
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        folders = {
            str(item.get("id", ""))
            for item in self.client.folders(self.config.mailbox_id)
        }
        expected = set(self.config.folder_ids)
        return VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED
            if expected <= folders
            else VerificationStatus.FAILED,
            "Exact configured mailbox folders were checked read-only.",
            len(expected),
            len(expected & folders),
            ("body-excluded", "attachments-excluded"),
        )

    def evidence_ref(self, message: OutlookMessage) -> EvidenceRef:
        if message.mailbox_id != self.config.mailbox_id:
            raise ValueError("message mailbox does not match configured source")
        folder = next(
            (
                item
                for item in self.config.folder_identities
                if item.provider_id == message.folder_id
            ),
            None,
        )
        if folder is None:
            raise ValueError("message folder has no configured identity mapping")
        source = SourceRef(
            folder.authority_id,
            CONNECTOR_ID,
            folder.authority_id,
            "Microsoft 365 Outlook Mail",
            provider_resource_id=folder.provider_id,
        )
        record = UniversalRecordRef(
            source,
            message.message_id,
            message.security_domain,
            message.classification,
            "communication.email.metadata",
            message.web_url,
            message.last_modified_at.isoformat(),
        )
        digest = hashlib.sha256(
            json.dumps([folder.authority_id, message.message_id]).encode()
        ).hexdigest()
        return EvidenceRef(
            f"outlook-{digest}",
            record,
            locator=f"folder:{folder.authority_id};received:{message.received_at.isoformat()}",
            transformation_id="outlook-mail-metadata",
            transformation_version=CONNECTOR_VERSION,
        )

    def admission_provenance(
        self, message: OutlookMessage, result: OutlookRetrievalResult
    ) -> tuple[EvidenceRef, ...]:
        return (
            self.evidence_ref(message),
            *(
                ref
                for decision in result.decisions
                if decision.record_key == message.message_id
                and decision.outcome is AdmissionOutcome.ADMITTED
                for ref in decision.relationship_evidence
            ),
        )

    def _validate_request(self, request: ConnectorRequest) -> None:
        if request.security_domain != self.config.security_domain:
            raise PermissionError("mail domain does not match approved source")
        if request.classification != self.config.classification:
            raise PermissionError("mail classification does not match source")
        expected = {
            self.config.authority_id,
            *self.config.authority_folders,
            *self.admission_scope,
        }
        if not expected <= set(request.scope):
            raise PermissionError(
                "request is not bound to the configured mailbox scope"
            )

    def _message(self, item: dict[str, Any]) -> OutlookMessage | None:
        categories = tuple(str(value) for value in item.get("categories", ()))
        if (
            self.config.scope_mode is MailScopeMode.CATEGORY_REQUIRED
            and self.config.required_category not in categories
        ):
            return None
        if "body" in item or "bodyPreview" in item or "attachments" in item:
            raise ValueError(
                "Graph mail payload exceeded the PA-003 metadata projection"
            )
        folder_id = str(item.get("parentFolderId", ""))
        if folder_id not in self.config.folder_ids:
            return None
        return OutlookMessage(
            str(item["id"]),
            self.config.mailbox_id,
            folder_id,
            str(item.get("subject") or "(No subject)"),
            _address(item.get("from")),
            tuple(_address(value) for value in item.get("toRecipients", ())),
            _timestamp(item["receivedDateTime"]),
            _timestamp(item["lastModifiedDateTime"]),
            str(item.get("importance", "normal")),
            item.get("isRead") is True,
            categories,
            None if item.get("webLink") is None else str(item["webLink"]),
            self.config.security_domain,
            self.config.classification,
        )


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Graph mail timestamp must be timezone-aware")
    return parsed


def _address(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("emailAddress", {}).get("address", ""))


def _window_from_scope(scope: tuple[str, ...]) -> MailWindow:
    values = [
        item.removeprefix("window:") for item in scope if item.startswith("window:")
    ]
    return MailWindow(values[0]) if len(values) == 1 else MailWindow.LAST_7_DAYS
