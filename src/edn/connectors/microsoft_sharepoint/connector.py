"""Synthetic-only read-only SharePoint Business OS connector."""

from __future__ import annotations

import hashlib
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
from edn.connectors.microsoft_sharepoint.client import GraphSharePointClient
from edn.connectors.microsoft_sharepoint.models import (
    SharePointConfig,
    SharePointRecord,
    SharePointRetrievalResult,
)
from edn.core import CapabilityManifest, EvidenceRef, SourceRef, UniversalRecordRef

CONNECTOR_ID = "microsoft-sharepoint"
CONNECTOR_VERSION = "0.1.0"
READ_PERMISSION = "Sites.Selected"


class MicrosoftSharePointConnector:
    def __init__(self, config: SharePointConfig, client: GraphSharePointClient) -> None:
        self.config = config
        self.client = client
        capabilities = (
            CapabilityManifest(
                "sharepoint.search",
                "microsoft-graph",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                frozenset({"search"}),
                frozenset({READ_PERMISSION}),
                frozenset({config.security_domain.domain_id}),
                "read",
            ),
            CapabilityManifest(
                "sharepoint.verify",
                "microsoft-graph",
                CONNECTOR_ID,
                CONNECTOR_VERSION,
                frozenset({"verify"}),
                frozenset({READ_PERMISSION}),
                frozenset({config.security_domain.domain_id}),
                "read",
            ),
        )
        self._manifest = ConnectorManifest(
            CONNECTOR_ID,
            CONNECTOR_VERSION,
            "Microsoft 365 SharePoint Business OS",
            "microsoft-graph",
            "Bounded list-item retrieval; no schema or item mutation.",
            "business-records",
            capabilities,
            frozenset({"search", "verify"}),
            "urn:edn:schema:microsoft-sharepoint-config:1",
            "1.0.0",
        )

    @property
    def manifest(self) -> ConnectorManifest:
        return self._manifest

    def search_records(
        self,
        request: ConnectorRequest,
        *,
        query: str,
        now: datetime,
        limit: int,
    ) -> SharePointRetrievalResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if not query.strip():
            raise ValueError("SharePoint query must not be blank")
        if not 1 <= limit <= 25:
            raise ValueError("SharePoint retrieval limit must be between 1 and 25")
        raw = self.client.search_items(
            self.config.site_id,
            self.config.list_id,
            query.strip(),
            self.config.allowed_fields,
            limit=limit,
        )
        admitted = tuple(
            record
            for item in raw
            for record in (self._record(item, now),)
            if record is not None
        )
        return SharePointRetrievalResult(len(raw), admitted)

    def search(self, request: ConnectorRequest) -> SearchResult:
        query = next(
            (
                value.removeprefix("query:")
                for value in request.scope
                if value.startswith("query:")
            ),
            "current business records",
        )
        result = self.search_records(
            request, query=query, now=datetime.now(UTC), limit=25
        )
        return SearchResult(
            request.request_id,
            tuple(self.evidence_ref(item) for item in result.records),
        )

    def verify(self, request: ConnectorRequest) -> VerificationResult:
        require_supported_operation(self, request)
        self._validate_request(request)
        fields = set(self.client.list_fields(self.config.site_id, self.config.list_id))
        expected = set(self.config.allowed_fields)
        return VerificationResult(
            request.request_id,
            VerificationStatus.VERIFIED
            if expected <= fields
            else VerificationStatus.FAILED,
            "Exact configured site, list and read projection checked.",
            len(expected),
            len(expected & fields),
            ("read-only", "mutation-unavailable"),
        )

    def evidence_ref(self, item: SharePointRecord) -> EvidenceRef:
        source = SourceRef(
            "microsoft-sharepoint.business-os",
            CONNECTOR_ID,
            f"{self.config.site_id}:{self.config.list_id}",
            self.config.list_name,
        )
        record = UniversalRecordRef(
            source,
            item.item_id,
            item.security_domain,
            item.classification,
            "business.record.sharepoint",
            item.web_url,
            item.etag or item.modified_at.isoformat(),
        )
        digest = hashlib.sha256(
            f"{self.config.site_id}:{self.config.list_id}:{item.item_id}".encode()
        ).hexdigest()
        field_names = ",".join(name for name, _ in item.fields)
        return EvidenceRef(
            f"sharepoint-{digest}",
            record,
            locator=(
                f"fields:{field_names};security:{item.security_value};"
                f"modified:{item.modified_at.isoformat()};"
                f"retrieved:{item.retrieved_at.isoformat()}"
            ),
            transformation_id="sharepoint-field-projection",
            transformation_version=CONNECTOR_VERSION,
        )

    def _validate_request(self, request: ConnectorRequest) -> None:
        if request.security_domain != self.config.security_domain:
            raise PermissionError("SharePoint domain does not match source")
        if request.classification != self.config.classification:
            raise PermissionError("SharePoint classification does not match source")
        if not {self.config.site_id, self.config.list_id} <= set(request.scope):
            raise PermissionError("request is not bound to the configured list")

    def _record(self, item: dict[str, Any], now: datetime) -> SharePointRecord | None:
        forbidden = {"driveItem", "content", "versions", "permissions"}
        if forbidden & item.keys():
            raise ValueError("SharePoint payload exceeded the field projection")
        fields = item.get("fields")
        if not isinstance(fields, dict):
            raise ValueError("SharePoint item fields must be an object")
        security_value = str(fields.get(self.config.security_field, ""))
        if security_value != self.config.expected_security_value:
            return None
        projected = tuple(
            (name, str(fields[name]))
            for name in self.config.allowed_fields
            if name in fields
        )
        return SharePointRecord(
            str(item["id"]),
            str(fields.get("Title") or "(Untitled record)"),
            projected,
            _timestamp(item["lastModifiedDateTime"]),
            now,
            security_value,
            None if item.get("webUrl") is None else str(item["webUrl"]),
            None if item.get("eTag") is None else str(item["eTag"]),
            self.config.security_domain,
            self.config.classification,
        )


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("SharePoint timestamp must be timezone-aware")
    return parsed
