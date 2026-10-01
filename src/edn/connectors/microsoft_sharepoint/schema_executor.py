"""One-shot schema inspection, isolated from operational SharePoint connectors.

No authentication or consent implementation. The optional HTTP transport accepts
an already authorized token supplier and permits only the planner's exact GETs.
Callers must establish identity, consent and protected storage before invoking it.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import os
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import IO, Any, Protocol
from urllib.parse import unquote, urlsplit
from uuid import UUID

from edn.connectors.microsoft_sharepoint.schema_plan import (
    CANDIDATE_LISTS,
    HOST,
    SITE_URL,
    SchemaRequest,
    list_schema_requests,
    site_identity_request,
)

MAX_BYTES = 1_048_576
ARTIFACT_NAME = "schema-inspection.json"
TENANT = "aae6ab79-45eb-4829-a04f-595becdb936d"
APPLICATION = "2381e4f6-44bc-4697-ad64-e86513cb9dee"
ACCOUNT = "elliot@ednsystems.com.au"


class SchemaInspectionError(ValueError):
    """Static error codes only: never copy provider content into error/audit text."""


class SchemaMode(Enum):
    FULL = "full_schema_inspection"
    PROJECTS_DIAGNOSTIC = "projects_schema_diagnostic"

    @property
    def budget(self) -> int:
        return 3 if self is SchemaMode.PROJECTS_DIAGNOSTIC else 7


def require_mode(mode: SchemaMode) -> SchemaMode:
    if not isinstance(mode, SchemaMode):
        raise SchemaInspectionError("invalid_execution_mode")
    return mode


FAILURE_CATEGORIES = {
    "invalid_token_input": "authentication_authorization",
    "http_authorization": "authentication_authorization",
    "http_status": "http_status",
    "graph_error": "graph_error",
    "malformed_json": "malformed_json",
    "duplicate_json_key": "malformed_json",
    "invalid_object": "unexpected_response_shape",
    "invalid_text": "unexpected_response_shape",
    "invalid_schema_property": "unexpected_response_shape",
    **dict.fromkeys(
        (
            "columns_top_level_not_object",
            "columns_value_missing",
            "columns_value_not_array",
            "columns_empty",
            "columns_limit_exceeded",
            "column_record_not_object",
            "column_required_field_type_invalid",
            "column_facet_shape_invalid",
            "column_unexpected_shape",
        ),
        "unexpected_response_shape",
    ),
    "column_required_field_missing": "projection_field_incompatibility",
    "column_type_facet_ambiguous": "unsupported_schema_facet",
    "column_type_facet_unsupported": "unsupported_schema_facet",
    "missing_column_property": "projection_field_incompatibility",
    "unknown_or_ambiguous_column_type": "unsupported_schema_facet",
    "operational_content": "prohibited_content",
    "continuation_prohibited": "pagination",
    "redirect_prohibited": "redirect",
    "content_type": "unexpected_response_shape",
    "content_encoding_prohibited": "unexpected_response_shape",
    "response_size": "unexpected_response_shape",
    "list_identity_mismatch": "identity_verification",
    "list_url_mismatch": "identity_verification",
    "list_template_mismatch": "identity_verification",
    "duplicate_column_identity": "identity_verification",
    "invalid_schema_identifier": "unexpected_response_shape",
    "missing_schema_property": "projection_field_incompatibility",
    "site_identity_mismatch": "identity_verification",
    "request_not_allowlisted": "prohibited_content",
    "request_order_or_budget": "prohibited_content",
    "transport_budget_or_replay": "prohibited_content",
    "transport_exception": "transport",
    "audit_write_failed": "persistence_audit",
    "internal_failure": "internal_executor",
}
GRAPH_CODES = frozenset(
    {
        "accessDenied",
        "Authorization_RequestDenied",
        "InvalidAuthenticationToken",
        "invalidRequest",
        "BadRequest",
        "Request_BadRequest",
        "itemNotFound",
        "notSupported",
        "generalException",
        "serviceNotAvailable",
        "tooManyRequests",
    }
)


def diagnostic() -> dict[str, Any]:
    return dict(
        stage="prepared",
        network_dispatch_started=False,
        network_dispatch_completed=False,
        response_received=False,
        http_status=None,
        content_type=None,
        response_bytes=None,
        request_id=None,
        client_request_id=None,
        json_parsed=False,
        validated_records=0,
        column_ordinal=None,
        column_facet=None,
        graph_error_code=None,
        failure_category=None,
        failure_reason=None,
        pagination_rejected=False,
        redirect_rejected=False,
        prohibited_content_rejected=False,
    )


def record_failure(info: dict[str, Any], exc: Exception) -> None:
    reason = "internal_failure"
    if isinstance(exc, SchemaInspectionError) and len(exc.args) == 1:
        candidate = exc.args[0]
        if isinstance(candidate, str) and candidate in FAILURE_CATEGORIES:
            reason = candidate
    elif isinstance(exc, (OSError, http.client.HTTPException)):
        reason = "transport_exception"
    info.update(
        failure_reason=reason,
        failure_category=FAILURE_CATEGORIES[reason],
        pagination_rejected=reason == "continuation_prohibited",
        redirect_rejected=reason == "redirect_prohibited",
        prohibited_content_rejected=reason == "operational_content",
    )


def safe_uuid(value: object) -> str | None:
    if isinstance(value, str) and len(value) == 36:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return None


@dataclass(frozen=True, slots=True)
class SchemaIdentity:
    """Verified host input; constructing it does not authenticate or verify a grant."""

    tenant: str
    application: str
    account: str
    scopes: frozenset[str]
    grant_id: str
    grant_role: str = "read"

    def __post_init__(self) -> None:
        if (self.tenant, self.application, self.account) != (
            TENANT,
            APPLICATION,
            ACCOUNT,
        ):
            raise SchemaInspectionError("identity_mismatch")
        if self.scopes != frozenset({"Sites.Selected"}):
            raise SchemaInspectionError("runtime_scope_mismatch")
        if self.grant_role != "read":
            raise SchemaInspectionError("grant_role_mismatch")
        _text(self.grant_id)


@dataclass(frozen=True, slots=True)
class SchemaReply:
    status: int
    body: bytes


class SchemaTransport(Protocol):
    def get(self, request: SchemaRequest) -> SchemaReply: ...


def validate_schema_request(request: SchemaRequest) -> None:
    """Exact semantic plan equality, not substring/path-prefix authorization."""
    if request == site_identity_request():
        return
    try:
        parts = urlsplit(request.url)
        path = parts.path.split("/")
        if parts.scheme != "https" or parts.netloc != "graph.microsoft.com":
            raise ValueError
        if len(path) < 5 or path[1:3] != ["v1.0", "sites"]:
            raise ValueError
        site_id = unquote(path[3])
        if request not in list_schema_requests(
            resolved_site_id=site_id, resolved_web_url=SITE_URL
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SchemaInspectionError("request_not_allowlisted") from None


class SchemaHttpTransport:
    """Fixed host HTTPS, no redirects, retries, cookie jar or generic URL opener.

    A second independent request guard caps even direct transport usage. This
    class never acquires a token and is not instantiated by imports or tests.
    """

    def __init__(
        self, token_supplier: Callable[[], str], mode: SchemaMode = SchemaMode.FULL
    ) -> None:
        self._mode = require_mode(mode)
        self._token_supplier = token_supplier
        self._used: set[str] = set()
        self._stopped = False
        self._lock = threading.Lock()
        self._sequence = _SchemaSequence(self._mode)
        self.diagnostic = diagnostic()

    def get(self, request: SchemaRequest) -> SchemaReply:
        with self._lock:
            if self._stopped:
                raise SchemaInspectionError("transport_stopped")
            self.diagnostic = diagnostic()
            info = self.diagnostic
            info["endpoint_class"] = (
                "list_columns" if request.purpose.startswith("columns_") else "identity"
            )
            try:
                validate_schema_request(request)
                self._sequence.require_next(request)
                if len(self._used) >= self._mode.budget or request.url in self._used:
                    raise SchemaInspectionError("transport_budget_or_replay")
                self._used.add(request.url)  # Consume before token/network work.
                token = self._token_supplier()
                if not token or "\r" in token or "\n" in token:
                    raise SchemaInspectionError("invalid_token_input")
                connection = http.client.HTTPSConnection(
                    "graph.microsoft.com", timeout=30
                )
                try:
                    url = urlsplit(request.url)
                    info.update(stage="dispatch", network_dispatch_started=True)
                    connection.request(
                        "GET",
                        url.path + "?" + url.query,
                        headers={
                            "Authorization": "Bearer " + token,
                            "Accept": "application/json",
                        },
                    )
                    info["network_dispatch_completed"] = True
                    info["stage"] = "response_headers"
                    response = connection.getresponse()
                    info.update(response_received=True, http_status=response.status)
                    media = response.getheader("Content-Type", "").split(";")[0]
                    info["content_type"] = (
                        media
                        if media in {"application/json", "text/html", "text/plain"}
                        else "other"
                    )
                    info["request_id"] = safe_uuid(response.getheader("request-id"))
                    info["client_request_id"] = safe_uuid(
                        response.getheader("client-request-id")
                    )
                    if (
                        300 <= response.status < 400
                        or response.getheader("Location") is not None
                    ):
                        raise SchemaInspectionError("redirect_prohibited")
                    if response.getheader("Content-Encoding") not in (None, "identity"):
                        raise SchemaInspectionError("content_encoding_prohibited")
                    if media != "application/json":
                        raise SchemaInspectionError("content_type")
                    info["stage"] = "response_body"
                    body = response.read(MAX_BYTES + 1)
                    info["response_bytes"] = min(len(body), MAX_BYTES + 1)
                    reply = SchemaReply(response.status, body)
                    value = _decode(reply, info)
                    info["stage"] = "schema_validation"
                    self._sequence.accept(request, value, info)
                    info["stage"] = "verified"
                    return reply
                finally:
                    connection.close()
            except Exception as exc:
                record_failure(info, exc)
                self._stopped = True
                raise SchemaInspectionError("transport_failed") from None


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise SchemaInspectionError("invalid_text")
    if any(ord(c) < 32 for c in value):
        raise SchemaInspectionError("invalid_text")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaInspectionError("invalid_object")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaInspectionError("duplicate_json_key")
        result[key] = value
    return result


def _no_continuation(value: object) -> None:
    if isinstance(value, dict):
        if any(k.lower() in {"@odata.nextlink", "@odata.deltalink"} for k in value):
            raise SchemaInspectionError("continuation_prohibited")
        if any(
            k.lower() in {"items", "fields", "attachments", "driveitems", "versions"}
            for k in value
        ):
            raise SchemaInspectionError("operational_content")
        for child in value.values():
            _no_continuation(child)
    elif isinstance(value, list):
        for child in value:
            _no_continuation(child)


def _decode(reply: SchemaReply, info: dict[str, Any] | None = None) -> dict[str, Any]:
    info = info if info is not None else diagnostic()
    info.update(
        response_received=True,
        http_status=reply.status,
        response_bytes=min(len(reply.body), MAX_BYTES + 1),
        stage="response_parsing",
    )
    if len(reply.body) > MAX_BYTES:
        raise SchemaInspectionError("response_size")
    try:
        value = json.loads(reply.body, object_pairs_hook=_pairs)
        info["json_parsed"] = True
    except SchemaInspectionError:
        raise
    except (ValueError, TypeError, RecursionError, UnicodeError):
        if reply.status != 200:
            raise SchemaInspectionError(
                "http_authorization" if reply.status in (401, 403) else "http_status"
            ) from None
        raise SchemaInspectionError("malformed_json") from None
    if not isinstance(value, dict) and info.get("endpoint_class") == "list_columns":
        raise SchemaInspectionError("columns_top_level_not_object")
    value = _object(value)
    error = value.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        info["graph_error_code"] = (
            code if isinstance(code, str) and code in GRAPH_CODES else "other"
        )
    if reply.status in (401, 403):
        raise SchemaInspectionError("http_authorization")
    if reply.status != 200:
        raise SchemaInspectionError(
            "graph_error" if error is not None else "http_status"
        )
    if error is not None:
        raise SchemaInspectionError("graph_error")
    info["stage"] = "content_guards"
    _no_continuation(value)
    return value


# Only these nested schema properties can survive serialization. Formula,
# defaultValue, formatting JSON, descriptions and arbitrary extension data cannot.
FACETS: dict[str, dict[str, str]] = {
    "text": {
        "allowMultipleLines": "bool",
        "appendChangesToExistingText": "bool",
        "linesForEditing": "int",
        "maxLength": "int",
        "textType": "str",
    },
    "number": {
        "decimalPlaces": "str",
        "displayAs": "str",
        "minimum": "number",
        "maximum": "number",
    },
    "dateTime": {"displayAs": "str", "format": "str"},
    "choice": {"allowTextEntry": "bool", "choices": "strings", "displayAs": "str"},
    "boolean": {},
    "lookup": {
        "allowMultipleValues": "bool",
        "allowUnlimitedLength": "bool",
        "columnName": "str",
        "listId": "str",
        "primaryLookupColumnId": "str",
    },
    "personOrGroup": {
        "allowMultipleSelection": "bool",
        "chooseFromType": "str",
        "displayAs": "str",
    },
    "currency": {"locale": "str"},
    "calculated": {"outputType": "str", "format": "str"},
    "hyperlinkOrPicture": {"isPicture": "bool"},
    "term": {"allowMultipleValues": "bool", "showFullyQualifiedName": "bool"},
}


def _project(value: object, fields: dict[str, str]) -> dict[str, Any]:
    source = _object(value)
    output: dict[str, Any] = {}
    for key, kind in fields.items():
        if key not in source:
            continue
        item = source[key]
        if kind == "str":
            output[key] = _text(item)
        elif (
            (kind == "bool" and type(item) is bool)
            or (kind == "int" and type(item) is int and item >= 0)
            or (kind == "number" and type(item) in (int, float) and math.isfinite(item))
        ):
            output[key] = item
        elif kind == "strings" and isinstance(item, list) and len(item) <= 1000:
            output[key] = [_text(entry) for entry in item]
        else:
            raise SchemaInspectionError("invalid_schema_property")
    return output


# Known unprojected metadata may be discarded; any other property is rejected
# rather than accidentally accepting a new, unsupported type facet.
COLUMN_METADATA = frozenset(
    {
        "@odata.context",
        "@odata.type",
        "columnGroup",
        "description",
        "defaultValue",
        "enforceUniqueValues",
        "indexed",
        "isDeletable",
        "isReorderable",
        "isSealed",
        "propagateChanges",
        "sourceContentType",
        "validation",
        "sourceColumn",
    }
)
UNSUPPORTED_FACETS = frozenset({"geolocation", "thumbnail", "contentApprovalStatus"})


def _column(value: object, info: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaInspectionError("column_record_not_object")
    source = value
    required = {
        "id": "str",
        "name": "str",
        "displayName": "str",
        "required": "bool",
        "readOnly": "bool",
        "hidden": "bool",
    }
    if any(key not in source for key in required):
        raise SchemaInspectionError("column_required_field_missing")
    try:
        output = _project(source, required)
        UUID(output["id"])
    except (SchemaInspectionError, ValueError):
        raise SchemaInspectionError("column_required_field_type_invalid") from None
    if any(source.get(key) is not None for key in UNSUPPORTED_FACETS):
        if info is not None:
            info["column_facet"] = "unsupported"
        raise SchemaInspectionError("column_type_facet_unsupported")
    if (
        source.keys()
        - required.keys()
        - FACETS.keys()
        - COLUMN_METADATA
        - UNSUPPORTED_FACETS
    ):
        raise SchemaInspectionError("column_unexpected_shape")
    kinds = [key for key in FACETS if source.get(key) is not None]
    if len(kinds) > 1:
        if info is not None:
            info["column_facet"] = "ambiguous"
        raise SchemaInspectionError("column_type_facet_ambiguous")
    if not kinds:
        # Graph documents base-only columns for types it cannot represent.
        # Preserve uncertainty explicitly; never infer a type or adapter capability.
        if info is not None:
            info["column_facet"] = "unavailable"
        output["type_status"] = "unavailable"
        return output
    kind = kinds[0]
    if info is not None:
        info["column_facet"] = kind
    try:
        output[kind] = _project(source[kind], FACETS[kind])
        if kind == "lookup":
            UUID(output[kind]["listId"])
            _text(output[kind]["columnName"])
    except (SchemaInspectionError, KeyError, ValueError):
        raise SchemaInspectionError("column_facet_shape_invalid") from None
    return output


class _SchemaSequence:
    """Shared identity/order guard for executor and actual HTTP boundary."""

    def __init__(self, mode: SchemaMode = SchemaMode.FULL) -> None:
        self._mode = require_mode(mode)
        self.plan: tuple[SchemaRequest, ...] = (site_identity_request(),)
        self.index = 0

    @property
    def next_request(self) -> SchemaRequest | None:
        return self.plan[self.index] if self.index < len(self.plan) else None

    def require_next(self, request: SchemaRequest) -> None:
        validate_schema_request(request)
        if self.index >= self._mode.budget or request != self.next_request:
            raise SchemaInspectionError("request_order_or_budget")

    def accept(
        self,
        request: SchemaRequest,
        value: dict[str, Any],
        info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require_next(request)
        projected: dict[str, Any]
        if self.index == 0:
            try:
                projected = {
                    k: _text(value[k]) for k in ("id", "displayName", "webUrl")
                }
            except KeyError:
                raise SchemaInspectionError("missing_schema_property") from None
            try:
                self.plan = (
                    site_identity_request(),
                    *list_schema_requests(
                        resolved_site_id=projected["id"],
                        resolved_web_url=projected["webUrl"],
                    ),
                )[: self._mode.budget]
            except ValueError:
                raise SchemaInspectionError("site_identity_mismatch") from None
        elif self.index % 2:
            name, identifier = CANDIDATE_LISTS[(self.index - 1) // 2]
            if value.get("id") != identifier or value.get("displayName") != name:
                raise SchemaInspectionError("list_identity_mismatch")
            if "webUrl" not in value or "list" not in value:
                raise SchemaInspectionError("missing_schema_property")
            web_url = _text(value["webUrl"])
            parsed = urlsplit(web_url)
            path = unquote(parsed.path)
            prefix = "/sites/EDNSystems/Lists/"
            tail = path.removeprefix(prefix)
            if (
                parsed.scheme != "https"
                or parsed.netloc != HOST
                or parsed.query
                or parsed.fragment
                or not path.startswith(prefix)
                or not tail
                or "/" in tail
                or "\\" in tail
                or tail in {".", ".."}
            ):
                raise SchemaInspectionError("list_url_mismatch")
            info = _project(
                value["list"],
                {"template": "str", "hidden": "bool", "contentTypesEnabled": "bool"},
            )
            if info.get("template") != "genericList":
                raise SchemaInspectionError("list_template_mismatch")
            projected = {
                "id": identifier,
                "displayName": name,
                "webUrl": web_url,
                "list": info,
            }
        else:
            if "value" not in value:
                raise SchemaInspectionError("columns_value_missing")
            columns = value["value"]
            if not isinstance(columns, list):
                raise SchemaInspectionError("columns_value_not_array")
            if not columns:
                raise SchemaInspectionError("columns_empty")
            if len(columns) > 100:
                raise SchemaInspectionError("columns_limit_exceeded")
            projected_columns = []
            for ordinal, column in enumerate(columns):
                if info is not None:
                    info.update(column_ordinal=ordinal, column_facet=None)
                projected_columns.append(_column(column, info))
                if info is not None:
                    info["validated_records"] = len(projected_columns)
            for key in ("id", "name"):
                if len({c[key].casefold() for c in projected_columns}) != len(columns):
                    raise SchemaInspectionError("duplicate_column_identity")
            projected = {"columns": projected_columns}
        self.index += 1
        return projected


class SchemaExecutor:
    """One attempt per object AND output directory, including failure/restart.

    The output directory must already exist under an owner-approved storage
    boundary. One exclusive artifact is also the durable no-retry marker.
    """

    def __init__(
        self,
        identity: SchemaIdentity,
        transport: SchemaTransport,
        mode: SchemaMode = SchemaMode.FULL,
    ) -> None:
        self._mode = require_mode(mode)
        self._identity = identity
        self._transport = transport
        self._started = False
        self._lock = threading.Lock()

    def run(self, output_directory: Path) -> Path:
        with self._lock:
            if self._started:
                raise SchemaInspectionError("attempt_already_started")
            self._started = True
        # ACL verification is a host prerequisite, not chmod or an ACL repair.
        if not output_directory.is_dir() or any(
            p.is_symlink()
            or bool(
                getattr(p.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            )
            for p in (output_directory, *output_directory.parents)
        ):
            raise SchemaInspectionError("storage_boundary")
        if any(output_directory.iterdir()):
            raise SchemaInspectionError("storage_not_empty_or_prior_attempt")
        destination = output_directory / ARTIFACT_NAME
        try:
            handle = destination.open("x", encoding="utf-8", newline="\n")
        except OSError:
            raise SchemaInspectionError("artifact_exists_or_storage_denied") from None
        started = datetime.now(UTC)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "run_id": output_directory.name,
            "artifact_created_at": started.isoformat(),
            "started_at": started.isoformat(),
            "delete_by": (started + timedelta(days=7)).isoformat(),
            "state": "started",
            "request_budget": self._mode.budget,
            "execution_mode": self._mode.value,
            "tenant": self._identity.tenant,
            "application": self._identity.application,
            "account": self._identity.account,
            "scope": "Sites.Selected",
            "grant_id": self._identity.grant_id,
            "grant_role": "read",
            "requests": [],
            "site": None,
            "lists": [],
        }
        with handle:
            self._save(handle, manifest)
            try:
                sequence = _SchemaSequence(self._mode)
                while (request := sequence.next_request) is not None:
                    value = self._get(request, manifest, handle)
                    entry = manifest["requests"][-1]
                    entry["diagnostic"]["stage"] = "schema_validation"
                    projected = sequence.accept(request, value, entry["diagnostic"])
                    entry["diagnostic"]["stage"] = "verified"
                    manifest["requests"][-1]["state"] = "verified"
                    if request.purpose == "resolve_candidate_site":
                        manifest["site"] = projected
                    elif request.purpose.startswith("verify_"):
                        manifest["lists"].append(projected)
                    else:
                        manifest["lists"][-1].update(projected)
                        count = len(projected["columns"])
                        manifest["requests"][-1]["column_count"] = count
                        manifest["requests"][-1]["at_column_cap"] = count == 100
                manifest["state"] = "complete"
                manifest["schema_sha256"] = hashlib.sha256(
                    json.dumps(
                        {"site": manifest["site"], "lists": manifest["lists"]},
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
            except Exception as exc:
                if manifest["requests"]:
                    info = manifest["requests"][-1]["diagnostic"]
                    if info["failure_reason"] is None:
                        record_failure(info, exc)
                manifest["state"] = "stopped"
                manifest["error"] = "schema_inspection_failed"
                self._save(handle, manifest)
                raise SchemaInspectionError("schema_inspection_failed") from None
            self._save(handle, manifest)
        return destination

    def _get(
        self, request: SchemaRequest, manifest: dict[str, Any], handle: IO[str]
    ) -> dict[str, Any]:
        validate_schema_request(request)
        audit = manifest["requests"]
        if len(audit) >= self._mode.budget or any(
            r["purpose"] == request.purpose for r in audit
        ):
            raise SchemaInspectionError("request_budget_or_replay")
        entry: dict[str, Any] = {
            "sequence": len(audit) + 1,
            "method": "GET",
            "endpoint_class": (
                "site_identity"
                if request.purpose == "resolve_candidate_site"
                else "list_columns"
                if request.purpose.startswith("columns_")
                else "list_identity"
            ),
            "diagnostic": diagnostic(),
            "purpose": request.purpose,
            "at": datetime.now(UTC).isoformat(),
            "state": "attempted",
        }
        audit.append(entry)
        self._save(handle, manifest)  # Durable attempt before even a failing GET.
        try:
            reply = self._transport.get(request)
        finally:
            if isinstance(self._transport, SchemaHttpTransport):
                entry["diagnostic"] = self._transport.diagnostic.copy()
        entry["diagnostic"]["endpoint_class"] = entry["endpoint_class"]
        value = _decode(reply, entry["diagnostic"])
        entry["state"] = "received"
        return value

    @staticmethod
    def _save(handle: IO[str], manifest: dict[str, Any]) -> None:
        try:
            SchemaExecutor._write_manifest(handle, manifest)
        except Exception:
            raise SchemaInspectionError("audit_write_failed") from None

    @staticmethod
    def _write_manifest(handle: IO[str], manifest: dict[str, Any]) -> None:
        content = {k: v for k, v in manifest.items() if k != "manifest_content_sha256"}
        manifest["manifest_content_sha256"] = hashlib.sha256(
            json.dumps(
                content, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        handle.seek(0)
        json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
