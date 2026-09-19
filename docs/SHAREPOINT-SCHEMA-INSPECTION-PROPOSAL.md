# Proposed one-shot SharePoint schema inspection — NOT AUTHORIZED OR EXECUTED

Prepared 17 September 2026. This is a metadata-only request plan. The new planner
has no network transport, token acquisition, permission enumeration or execution
entry point. Endpoint contracts and permission compatibility have not been
verified against live Microsoft services in this local-only session.

## Identity and permission gate

- Tenant: `aae6ab79-45eb-4829-a04f-595becdb936d`.
- Existing public client: `2381e4f6-44bc-4697-ad64-e86513cb9dee`.
- Delegated account: `elliot@ednsystems.com.au`.
- Known prior pilot scopes: `User.Read`, `Calendars.Read`, `Mail.Read`.

**Those three scopes are insufficient for SharePoint site/list/column reads.**
No current token, additional consent or resource grant was inspected. Do not
authenticate expecting the pilot's existing scopes to cover this inspection.

Before a future attempt, obtain owner-provided evidence of an already-existing
compatible read permission and exact resource grant for this application/user.
The preferred candidate is an existing `Sites.Selected` read grant limited to
this site, with matching delegated user access. A selected permission alone is
not a resource grant. A list-selected permission does not by itself prove the
site-resolution request is permitted. Compatibility of the chosen selected
permission with each proposed endpoint must be verified before execution.
Existing broader site-read permission may be sufficient technically, but the
execution boundary must still stay at this exact site and these three lists.
Do not request `Sites.Read.All`, write/full-control permissions or admin consent
as an automatic remedy. If there is no existing suitable access, the smallest
next owner decision is a separate review of exact-site read-only access; this
proposal does not grant or provision it.

Permission evidence needed: principal/application/tenant, existing delegated
scope, exact granted resource and read role where selected access is used,
and effective user's existing access. Obtain that from an owner/admin's existing
records, not by invoking a broad grant-inventory or `/permissions` API. The
inspection's successful metadata GETs prove only those particular operations.
They do not prove a complete inventory of permissions. Unknown facts remain
explicitly unverified. A 401/403 stops the attempt; no consent escalation.

## Seven proposed bounded GETs

All paths below are relative to `https://graph.microsoft.com/v1.0`.
Query strings are shown decoded for review; the planner URL-encodes them.
No POST, PATCH, PUT, DELETE, batch, search, delta, `$expand`, `/items`, other sites,
or continuation requests are permitted.

1. Resolve only the candidate path:

   `GET /sites/edn123.sharepoint.com:/sites/EDNSystems?$select=id,displayName,webUrl`

   Maximum one site. Require exact web URL
   `https://edn123.sharepoint.com/sites/EDNSystems` and a composite site ID with
   host `edn123.sharepoint.com`, site-collection ID
   `b16e7eb5-e3de-4a1a-ba45-6807d771ff26`, and web ID
   `49cc1059-a4f6-42f7-88bd-9940503ae28f`. Record the returned
   composite ID as `SITE_ID`; never substitute the historical GUID alone.
   A mismatch stops for owner review, without discovery of alternative resources.

For each exact candidate list below, perform the identity GET, verify the
returned ID, display name and web URL under the expected site, then and only
then perform that list's columns GET. Unexpected names or paths stop for review.

| GET numbers | Expected display name | Exact LIST_ID |
|---|---|---|
| 2, 3 | Projects | `66944251-b9a3-40cc-9a59-05538e200c19` |
| 4, 5 | Clients | `3d55c612-9799-4462-9474-7f0ca5a10b24` |
| 6, 7 | Actions | `d7079aad-7f18-4164-8bd6-41f5629898bb` |

Identity request (maximum one list):

`GET /sites/{SITE_ID}/lists/{LIST_ID}?$select=id,displayName,webUrl,list`

Columns request (one page, at most 100 column definitions):

`GET /sites/{SITE_ID}/lists/{LIST_ID}/columns?$select=id,name,displayName,required,readOnly,hidden,text,number,dateTime,choice,boolean,lookup,personOrGroup,currency,calculated,hyperlinkOrPicture,term&$top=100`

`SITE_ID` must be URL-encoded as one segment. `LIST_ID` is substituted exactly
from the table. `list` supplies the basic list facet (such as template/hidden/
content-type enablement), not a full SharePoint settings inventory. Column facets
describe types and choices; `lookup` describes target list/column relationships.
Record these IDs without following lookup targets to other lists or reading rows.
Person/group facets describe schema only; do not resolve users or directory data.
No item values, attachment content, documents or financial data are requested.
Unsupported/unknown facets remain unknown; do not broaden the call ad hoc.

If the service returns continuation, report partial schema and do not follow it.
If any response exceeds its proposed cap, is malformed, omits necessary identity
or type information, redirects unexpectedly, or changes identity, stop. No blind
retry or field-guessing. Known IDs are candidates until the response is verified.

## Local artifacts and execution prerequisites

A future reviewed runner needs synthetic HTTP-contract tests and a frozen
request allowlist before live approval. This session deliberately supplies an
inert planner only; an execution runner is not hidden in the module.

Store only one schema/audit bundle in a separately confirmed owner-controlled
local directory outside Git/cloud sync, with restrictive access and a maximum
seven-day retention. Do not reuse or extend old pilot retention deadlines.
Required artifacts:

- execution manifest with exact approved identity, existing permission evidence,
  request list/caps, storage boundary and deletion deadline;
- site/list identity and schema JSON containing only the fields above;
- audit of request paths, UTC timestamps, response status, returned counts,
  truncation/continuation, unknown permission facts and zero-item-read assertion;
- review table of exact internal field names/types/required state/lookup targets,
  marking unverified mappings explicitly.

Never save tokens, authorization headers, passwords or session caches in the
bundle. This inspection cannot establish verified client senders or project
relationships: schemas contain no operational rows. A later bounded operational
read would require a separately reviewed field/query/principal manifest and new
authority. UWC remains outside every step.

## Proposed approval text, only after prerequisites are satisfied

> Authorize one manually invoked metadata-only inspection using tenant
> aae6ab79-45eb-4829-a04f-595becdb936d, application
> 2381e4f6-44bc-4697-ad64-e86513cb9dee and delegated account
> elliot@ednsystems.com.au, subject to the identity, existing-access, storage and
> tested-runner gates in SHAREPOINT-SCHEMA-INSPECTION-PROPOSAL.md. I have reviewed
> the exact existing permission/grant evidence and local artifact location in the
> frozen execution manifest. Allow only the seven bounded GETs defined there,
> with identity verification before dependent calls, one page per column query,
> no continuation or retries. Stop on any mismatch, missing permission, consent
> request, unexpected response, or unresolved storage boundary. No list items,
> operational rows, lookup-target reads, UWC, Microsoft writes, permission changes,
> provider calls or schedules. Retain the schema/audit artifacts for at most seven
> days and stop for owner review after this single attempt.

This text is a proposal. It neither establishes missing Microsoft access nor
authorizes execution during the Email Admission V2 implementation session.

## Owner-reviewed identity correction (2026-09-19)

Graph IDs represent `hostname,siteCollectionId,webId`. The accepted EDN identity is
`edn123.sharepoint.com,b16e7eb5-e3de-4a1a-ba45-6807d771ff26,49cc1059-a4f6-42f7-88bd-9940503ae28f`.
The historical GUID was the web ID, not the site-collection ID. The shared planner
now verifies all three exact components and the exact canonical URL
`https://edn123.sharepoint.com/sites/EDNSystems`; no trailing slash, query,
fragment, alternate casing or swapped components are accepted. Both execution
boundaries use this verification before dependent requests. This local correction
confers no consent, selected-site assignment or live inspection authority.

Readiness: use the separate administrator context to inspect the accepted site's
assignment only after owner approval; create one read assignment only if absent,
stop on broader/duplicate grants, record its permission ID, and disconnect.
The EDN runtime retains delegated Sites.Selected without provisioning authority.
Before schema execution, require grant evidence, verified runtime identity/scopes,
protected seven-day storage and separate approval for the bounded seven GETs.
