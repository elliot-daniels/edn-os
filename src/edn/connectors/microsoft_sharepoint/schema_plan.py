"""Inert proposal for a separately authorized schema-only inspection.

No HTTP transport, authentication, item endpoint, grant enumeration or execution
entry point is provided. Candidate identifiers are not access authority.
"""

from dataclasses import dataclass
from urllib.parse import quote, urlencode
from uuid import UUID

HOST = "edn123.sharepoint.com"
SITE_URL = f"https://{HOST}/sites/EDNSystems"
WEB_ID = "49cc1059-a4f6-42f7-88bd-9940503ae28f"
SITE_COLLECTION_ID = "b16e7eb5-e3de-4a1a-ba45-6807d771ff26"
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
class GraphSiteIdentity:
    """Graph composite identity: hostname, site collection ID, then web ID."""

    hostname: str
    site_collection_id: str
    web_id: str
    web_url: str


EXPECTED_SITE = GraphSiteIdentity(HOST, SITE_COLLECTION_ID, WEB_ID, SITE_URL)


def verify_site_identity(site_id: str, web_url: str) -> GraphSiteIdentity:
    parts = site_id.split(",")
    if len(parts) != 3:
        raise ValueError("Graph site ID requires exactly three components")
    hostname, site_collection_id, web_id = parts
    # Require canonical GUID text as well as exact component semantics.
    if any(str(UUID(value)) != value for value in (site_collection_id, web_id)):
        raise ValueError("noncanonical Graph site ID component")
    identity = GraphSiteIdentity(hostname, site_collection_id, web_id, web_url)
    if identity != EXPECTED_SITE:
        raise ValueError("site identity mismatch; owner review required")
    return identity


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
    verify_site_identity(resolved_site_id, resolved_web_url)
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
