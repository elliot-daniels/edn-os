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

    def __init__(self, token_supplier: Callable[[], str]) -> None:
        self._token_supplier = token_supplier
        self._used: set[str] = set()
        self._stopped = False
        self._lock = threading.Lock()
        self._sequence = _SchemaSequence()

    def get(self, request: SchemaRequest) -> SchemaReply:
        with self._lock:
            if self._stopped:
                raise SchemaInspectionError("transport_stopped")
            try:
                validate_schema_request(request)
                self._sequence.require_next(request)
                if len(self._used) >= 7 or request.url in self._used:
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
                    connection.request(
                        "GET",
                        url.path + "?" + url.query,
                        headers={
                            "Authorization": "Bearer " + token,
                            "Accept": "application/json",
                        },
                    )
                    response = connection.getresponse()
                    if response.status != 200:
                        raise SchemaInspectionError("http_status")
                    if response.getheader("Location") is not None:
                        raise SchemaInspectionError("redirect_prohibited")
                    if response.getheader("Content-Encoding") not in (None, "identity"):
                        raise SchemaInspectionError("content_encoding_prohibited")
                    if (
                        response.getheader("Content-Type", "").split(";")[0]
                        != "application/json"
                    ):
                        raise SchemaInspectionError("content_type")
                    body = response.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise SchemaInspectionError("response_size")
                    reply = SchemaReply(response.status, body)
                    self._sequence.accept(request, _decode(reply))
                    return reply
                finally:
                    connection.close()
            except Exception:
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


def _decode(reply: SchemaReply) -> dict[str, Any]:
    if reply.status != 200:
        raise SchemaInspectionError("http_status")
    if len(reply.body) > MAX_BYTES:
        raise SchemaInspectionError("response_size")
    try:
        value = _object(json.loads(reply.body, object_pairs_hook=_pairs))
        _no_continuation(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise SchemaInspectionError("invalid_response") from None


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


def _column(value: object) -> dict[str, Any]:
    source = _object(value)
    required = {
        "id": "str",
        "name": "str",
        "displayName": "str",
        "required": "bool",
        "readOnly": "bool",
        "hidden": "bool",
    }
    output = _project(source, required)
    if output.keys() != required.keys():
        raise SchemaInspectionError("missing_column_property")
    UUID(output["id"])
    kinds = [key for key in FACETS if key in source and source[key] is not None]
    if len(kinds) != 1:
        raise SchemaInspectionError("unknown_or_ambiguous_column_type")
    kind = kinds[0]
    output[kind] = _project(source[kind], FACETS[kind])
    if kind == "lookup":
        UUID(output[kind]["listId"])
        _text(output[kind]["columnName"])
    return output


class _SchemaSequence:
    """Shared identity/order guard for executor and actual HTTP boundary."""

    def __init__(self) -> None:
        self.plan: tuple[SchemaRequest, ...] = (site_identity_request(),)
        self.index = 0

    @property
    def next_request(self) -> SchemaRequest | None:
        return self.plan[self.index] if self.index < len(self.plan) else None

    def require_next(self, request: SchemaRequest) -> None:
        validate_schema_request(request)
        if self.index >= 7 or request != self.next_request:
            raise SchemaInspectionError("request_order_or_budget")

    def accept(self, request: SchemaRequest, value: dict[str, Any]) -> dict[str, Any]:
        self.require_next(request)
        projected: dict[str, Any]
        if self.index == 0:
            projected = {k: _text(value[k]) for k in ("id", "displayName", "webUrl")}
            self.plan = (
                site_identity_request(),
                *list_schema_requests(
                    resolved_site_id=projected["id"],
                    resolved_web_url=projected["webUrl"],
                ),
            )
        elif self.index % 2:
            name, identifier = CANDIDATE_LISTS[(self.index - 1) // 2]
            if value.get("id") != identifier or value.get("displayName") != name:
                raise SchemaInspectionError("list_identity_mismatch")
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
            columns = value.get("value")
            if not isinstance(columns, list) or not 1 <= len(columns) <= 100:
                raise SchemaInspectionError("column_limit_or_shape")
            projected_columns = [_column(c) for c in columns]
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

    def __init__(self, identity: SchemaIdentity, transport: SchemaTransport) -> None:
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
        destination = output_directory / ARTIFACT_NAME
        try:
            handle = destination.open("x", encoding="utf-8", newline="\n")
        except OSError:
            raise SchemaInspectionError("artifact_exists_or_storage_denied") from None
        started = datetime.now(UTC)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "started_at": started.isoformat(),
            "delete_by": (started + timedelta(days=7)).isoformat(),
            "state": "started",
            "request_budget": 7,
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
                sequence = _SchemaSequence()
                while (request := sequence.next_request) is not None:
                    value = self._get(request, manifest, handle)
                    projected = sequence.accept(request, value)
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
            except Exception:
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
        if len(audit) >= 7 or any(r["url"] == request.url for r in audit):
            raise SchemaInspectionError("request_budget_or_replay")
        entry = {
            "sequence": len(audit) + 1,
            "method": "GET",
            "url": request.url,
            "purpose": request.purpose,
            "at": datetime.now(UTC).isoformat(),
            "state": "attempted",
        }
        audit.append(entry)
        self._save(handle, manifest)  # Durable attempt before even a failing GET.
        reply = self._transport.get(request)
        value = _decode(reply)
        entry["state"] = "received"
        return value

    @staticmethod
    def _save(handle: IO[str], manifest: dict[str, Any]) -> None:
        handle.seek(0)
        json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
