"""Inert proposal for a separately authorized schema-only inspection.

No HTTP transport, authentication, item endpoint, grant enumeration or execution
entry point is provided. Candidate identifiers are not access authority.
"""

from dataclasses import dataclass
from urllib.parse import quote, urlencode
from uuid import UUID

HOST = "edn123.sharepoint.com"
SITE_URL = f"https://{HOST}/sites/EDNSystems"
HISTORICAL_SITE_GUID = "49cc1059-a4f6-42f7-88bd-9940503ae28f"
CANDIDATE_LISTS = (
    ("Projects", "66944251-b9a3-40cc-9a59-05538e200c19"),
    ("Clients", "3d55c612-9799-4462-9474-7f0ca5a10b24"),
    ("Actions", "d7079aad-7f18-4164-8bd6-41f5629898bb"),
)
COLUMN_FIELDS = (
    "id",
    "name",
    "displayName",
    "required",
    "readOnly",
    "hidden",
    "text",
    "number",
    "dateTime",
    "choice",
    "boolean",
    "lookup",
    "personOrGroup",
    "currency",
    "calculated",
    "hyperlinkOrPicture",
    "term",
)


@dataclass(frozen=True, slots=True)
class SchemaRequest:
    purpose: str
    url: str
    maximum_records: int
    method: str = "GET"
    follow_continuation: bool = False


def site_identity_request() -> SchemaRequest:
    return SchemaRequest(
        "resolve_candidate_site",
        f"https://graph.microsoft.com/v1.0/sites/{HOST}:/sites/EDNSystems?"
        + urlencode({"$select": "id,displayName,webUrl"}),
        1,
    )


def list_schema_requests(
    *, resolved_site_id: str, resolved_web_url: str
) -> tuple[SchemaRequest, ...]:
    parts = resolved_site_id.split(",")
    if len(parts) != 3 or parts[0] != HOST or resolved_web_url != SITE_URL:
        raise ValueError(
            "site identity differs from the candidate; owner review required"
        )
    if str(UUID(parts[1])) != HISTORICAL_SITE_GUID:
        raise ValueError("historical site GUID differs; do not search other sites")
    UUID(parts[2])
    base = "https://graph.microsoft.com/v1.0/sites/" + quote(resolved_site_id, safe="")
    requests = []
    for name, identifier in CANDIDATE_LISTS:
        path = base + "/lists/" + identifier
        requests.append(
            SchemaRequest(
                "verify_" + name,
                path + "?" + urlencode({"$select": "id,displayName,webUrl,list"}),
                1,
            )
        )
        requests.append(
            SchemaRequest(
                "columns_" + name,
                path
                + "/columns?"
                + urlencode({"$select": ",".join(COLUMN_FIELDS), "$top": "100"}),
                100,
            )
        )
    return tuple(requests)


def permission_readiness(granted_scopes: frozenset[str]) -> str:
    """A scope name alone never proves a site/list grant or effective user access."""
    scopes = {
        value.removeprefix("https://graph.microsoft.com/") for value in granted_scopes
    }
    if not scopes & {
        "Sites.Read.All",
        "Sites.ReadWrite.All",
        "Sites.FullControl.All",
        "Sites.Selected",
        "Lists.SelectedOperations.Selected",
    }:
        return "blocked_missing_sharepoint_read_permission"
    return "unverified_requires_existing_grant_and_effective_access_evidence"
