# Bounded SharePoint schema executor — local/synthetic validation

Starting checkpoint: `a7a7058f85af0ad0d7aef85bf24b856a83566daa` on
`feature/executive-brief-reliability`. No Microsoft authentication, provisioning,
consent, grant inspection or live schema access occurred. Email Admission V2,
Core security validation, the inert planner and the operational SharePoint
connector are unchanged.

## Execution architecture

`schema_executor.py` consumes the existing `schema_plan.py` request definitions.
It is a dedicated inspection path, not an alternate operational connector.
There is no import or invocation of `MicrosoftSharePointConnector`, no registry
activation, authentication code, CLI auto-run, background worker or schedule.

The host supplies a `SchemaIdentity` containing the previously verified tenant,
application, delegated account, exact `Sites.Selected` scope and recorded read
grant ID. Construction validates the frozen expected values; **it does not
authenticate the caller, verify a token, query consent or prove a site grant**.
Those are owner-approved host prerequisites. Unexpected scope sets, identities or
write roles fail closed. No runtime provisioning authority is accepted.

`SchemaExecutor.run(existing_private_directory)` owns the sequence and audit.
Tests use a fake transport. `SchemaHttpTransport` provides the future HTTPS GET
boundary, accepting an already-authorized token supplier. That supplier must
return an existing in-memory token; it must not perform authentication, consent,
refresh/retries or its own network operations during the inspection. The transport
does not obtain credentials, parse auth caches or negotiate permissions itself.
No supplied transport can confer new inspection authority.

## Enforcement points

1. **Exact request equality.** Method, complete URL/query, purpose, maximum count
   and continuation flag must equal a planner request. Arbitrary hosts, paths,
   parameters, fragments, `$expand`, `/items`, drives, attachments, files,
   permissions and versions have no approved request form.
2. **Identity and order at two boundaries.** Both the executor and actual HTTP
   transport use the same sequence validator independently. Site response
   verification precedes all list calls. Each list's response is verified before
   its columns call. Calling the HTTP transport directly cannot skip those steps.
3. **Site identity.** Require exact HTTPS host/path via the frozen site request,
   exact returned site web URL, composite Graph ID, matching historical
   site-collection GUID and valid web GUID. No discovery/substitution fallback.
4. **List identity.** Require exact candidate ID and display name. Returned URL
   must be HTTPS on the expected host, beneath `/sites/EDNSystems/Lists/`, with
   one safe list-path segment and no query, fragment or traversal. Do not assume
   the list's URL slug equals its display name. Require `genericList`, not a
   document library. The actual slug is retained, never followed.
5. **Seven-request ceiling.** Both guards enforce the sequence/budget. Every
   transport URL is single-use. Failed requests consume their attempt. All
   HTTP failures stop the transport; there is no retry or token-refresh branch.
6. **No redirects or continuation.** The HTTP implementation uses a fixed-host
   `HTTPSConnection`, not a redirecting URL opener. Only status 200 and JSON are
   accepted. A Location header, compression, redirect status or any nested
   `@odata.nextLink`/`@odata.deltaLink` stops the attempt. No link is dereferenced.
7. **Bounded response.** Maximum 1 MiB per HTTP response; one through 100 columns
   per list. 100 without continuation is accepted with `at_column_cap: true`;
   101, empty/malformed collections, duplicate columns, absent required fields
   and unknown/ambiguous types stop. A cap is not a claim of tenant completeness.
8. **No raw persistence.** Explicit typed projections admit only necessary schema
   properties. Unknown properties are discarded. Operational-content properties
   such as items, fields, attachments and versions are rejected. JSON duplicate
   keys, malformed JSON and invalid schema values fail closed.
9. **No accidental replay.** The output file is created exclusively before any
   transport call. It is also the attempt marker. An existing file, even empty or
   truncated by an interrupted process, blocks a new instance. The same instance
   cannot run twice. Requests are recorded and flushed/fsynced before transport.
   There is no reset/delete/retry function.

The one-shot guard applies to this executor instance and chosen output directory.
It is not a global authorization ledger: deliberately creating another directory,
deleting a marker or constructing a separate transport requires separate owner
authority and is outside the approved host procedure. As with any injected
transport, arbitrary malicious Python supplied by a caller is outside this module's
security boundary. The provided HTTP transport is the enforced live boundary.

## Minimized output

Only `schema-inspection.json` is created in an existing owner-approved directory.
Symlink/reparse-point paths are rejected. The component does not create a different
directory, change ACLs, claim Windows ACL validation or relax protected-store rules.
The host must establish owner-controlled storage outside Git/cloud sync before
authentication and invocation. It must also prevent untrusted local replacement
of that directory while the run is active.

The artifact contains:

- expected runtime identity, recorded selected-site grant ID/role, start time and
  a maximum seven-day deletion deadline;
- ordered approved request URLs, purpose, timestamps and attempted/received/
  verified state, plus column count/cap flags;
- verified site ID/name/URL and list ID/name/URL with basic list configuration;
- column ID, internal name, display name, required/read-only/hidden flags and
  exactly one supported type facet;
- a SHA-256 over the filtered site/list schema on successful completion.

Nested facet projections are explicit in `FACETS`. They retain text constraints,
number/date formats, choice options, basic person/group settings, currency locale,
calculated output type/format, hyperlink mode, basic term flags and lookup target
list ID/column name/multiplicity. Lookup identities remain data and never become
requests. Descriptions, formulas, defaults, formatting JSON and arbitrary
extensions are not retained. Unknown types fail closed rather than being guessed.

Errors use fixed codes and never serialize exception messages, response bodies,
response headers, tokens or the token supplier. A stopped artifact may contain
already-verified partial schema. `complete` means the approved request sequence
completed, not that every SharePoint feature or semantic relationship is known.

## Synthetic seven-call transcript

The actual executor generated
[sharepoint-schema-synthetic.json](examples/sharepoint-schema-synthetic.json)
using fake responses only. Its synthetic web GUID is
`00000000-0000-0000-0000-000000000001`, not a discovered tenant identifier.
The artifact contains the full exact encoded URLs and one synthetic text column
per list. State: complete; exactly seven GETs; no other transport operation.

| Sequence | Purpose | Verified prerequisite |
|---|---|---|
| 1 | Resolve exact EDN Systems site | Frozen candidate path |
| 2 | Projects identity/configuration | Verified composite site ID |
| 3 | Projects columns, `$top=100` | Verified Projects ID/name/URL/template |
| 4 | Clients identity/configuration | Verified composite site ID |
| 5 | Clients columns, `$top=100` | Verified Clients ID/name/URL/template |
| 6 | Actions identity/configuration | Verified composite site ID |
| 7 | Actions columns, `$top=100` | Verified Actions ID/name/URL/template |

The tests separately drive the real HTTP transport with a mocked HTTPS connection,
confirming exact host/method/order, seven calls, no eighth call and no saved token.
An operational-connector constructor trap proves the normal connector is not
instantiated by the inspection. All tests deny unmocked HTTPS connections.

## Validation

- 94 new executor cases; 101 focused executor/planner tests passed.
- Full suite: **815 tests; 722 passed, 92 failed, 1 skipped**.
- Previous checkpoint: 628 passed, 92 failed, 1 skipped. All 94 added cases pass.
- Exact failure-ID comparison is recorded in `sharepoint-schema-validation.json`;
  zero new failures and zero missing baseline failures are required.
- Ruff and strict configured mypy pass (128 source files, Linux platform setting
  as used at the Windows baseline). Whitespace checks pass before commit.
- Existing POSIX security checks and Email Admission V2 are unchanged.

Files added: the executor module, its synthetic tests, this report/checklist,
the generated synthetic JSON example and the validation JSON. No existing
implementation file needs modification.

## Remaining uncertainties

No tenant identity, consent, grant, site/list ID or live response compatibility has
been verified here. Provisioning has not occurred. Unknown column facets,
omitted required schema flags, nonstandard list URLs, selected-permission service
behaviour and pagination can cause a safe stop. Do not fix those by expanding
permissions or requests during a live attempt. Graph schemas may describe a
relationship without proving any operational relationship; no client/project
rows have been inspected. Runtime authentication/identity verification and the
protected-storage approval remain responsibilities of the later reviewed host.

## OWNER PROVISIONING CHECKLIST — next step, not executed

### A. EDN application configuration

- Verify tenant `aae6ab79-45eb-4829-a04f-595becdb936d` and existing application
  `2381e4f6-44bc-4697-ad64-e86513cb9dee`.
- Configure Microsoft Graph **delegated `Sites.Selected`** only as the new
  SharePoint authority. No application permission, Sites.Read.All or full control.
- Record actual consent status and consent scope/principal. Establish Elliot's
  consent, or separately reviewed administrator consent if tenant policy requires
  it. Do not infer consent from the app registration's configured permissions.
- Preserve previous unrelated scopes. The inspection token must use exactly
  `Sites.Selected` as its Graph delegated data scope; do not use a provisioning
  token or silently accept a broader scope set.

### B. Separate administrator provisioning session

- Use separately approved administrator-controlled tooling, never the EDN runtime
  application. Verify the provisioner's identity, client ID, required authority
  and a supported rollback route before making any change.
- Resolve only `https://edn123.sharepoint.com/sites/EDNSystems`; verify the URL,
  composite Graph ID and candidate site-collection GUID
  `49cc1059-a4f6-42f7-88bd-9940503ae28f`. Stop on mismatch.
- Inspect existing application assignments on that site to avoid duplicates.
  This permission read belongs to provisioning, not the seven-call inspection.
- Reuse exactly one matching read assignment if it already exists. If absent,
  create exactly one site-level `read` assignment for the EDN application ID.
  Stop on duplicate, broader or ambiguous assignments; do not silently repair.
- Capture the exact permission ID, app ID, verified site ID, role and whether the
  assignment was newly created or reused. Verify the resulting assignment without
  reading list items. Existing user rights must permit the delegated access.
- Keep elevated provisioning permissions, tokens and credentials out of EDN OS.
  Disconnect, clear transient provisioning credentials, deactivate temporary admin
  roles and remove newly introduced temporary provisioning authority as approved.
  Signing out is not equivalent to revoking a persisted consent.
- Retain an administrator-controlled rollback procedure for the captured grant
  ID. Remove only newly added access when authorized; never delete reused grants
  or unrelated consent. Runtime self-provisioning/self-revocation is prohibited.

### C. Evidence needed before live inspection approval

- Reviewed executor commit, synthetic transcript, test results and exact seven
  request allowlist; no operational connector activation.
- Verified runtime tenant/application/account `elliot@ednsystems.com.au`, delegated
  selected scope, exact site read assignment and recorded permission ID.
- Separately verified authentication and token-to-account/application binding;
  do not treat `SchemaIdentity(...)` as proof. No additional Graph identity GET is
  hidden inside this executor or its seven-call budget.
- Reviewed host passing only an already-authorized in-memory token and verified
  inputs to the executor; no automatic auth, refresh, retries or provider calls.
- Owner-approved private directory outside Git/cloud sync, restrictive access,
  harmless create/read/delete validation and no existing attempt artifact. No ACL
  changes or alternative-directory workaround.
- Exact new artifact path and seven-day maximum retention; preserve every older
  artifact's deadline. No automated deletion or recurring schedule.
- Owner decision on whether newly added selected-site access is temporary or to
  remain. No retention of access is inferred from a successful inspection.
- A separate explicit one-shot live approval naming the above evidence. Stop on
  any mismatch/failure and after the single attempt; no pagination, retries,
  operational rows, Outlook/Calendar, UWC, provider calls or Microsoft writes.

This checklist does not authorize provisioning or inspection. The local build
session ends after validation and feature-branch publication.
