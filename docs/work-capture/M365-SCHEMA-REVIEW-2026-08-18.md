# Universal Work Capture V1 — Microsoft 365 schema review

Status: **read-only discovery complete; activation remains owner-gated**  
Review source: approved metadata-only inventory `2026-08-07-rerun-1` at the
approved external EDN Confidential location. No list items, document contents,
attachments, credentials, or webhook target URLs were copied into Git.

## Exact resources discovered

Site: `EDN Systems`, `https://edn123.sharepoint.com/sites/EDNSystems`, site ID
`49cc1059-a4f6-42f7-88bd-9940503ae28f`.

| Resource | Type | GUID | Relative URL | Versioning | Items | Key metadata |
|---|---|---|---|---:|---:|---|
| Work Log | GenericList | `7b6d10ec-c009-422a-9802-c907d3d4f57f` | `/sites/EDNSystems/Lists/WorkLog` | on | 0 | attachments on; indexes `InvoiceStatus`, `ProjectLookup`, `WorkDate` |
| Projects | GenericList | `66944251-b9a3-40cc-9a59-05538e200c19` | `/sites/EDNSystems/Lists/Projects` | on | 3 | attachments on; indexes `ClientLookup`, `ProjectCode`, `ProjectStatus` |
| Clients | GenericList | `3d55c612-9799-4462-9474-7f0ca5a10b24` | `/sites/EDNSystems/Lists/Clients` | on | 4 | attachments on |
| Actions | GenericList | `d7079aad-7f18-4164-8bd6-41f5629898bb` | `/sites/EDNSystems/Lists/Actions` | on | 3 | attachments on; indexes `ActionStatus`, `DueDate`, `ProjectLookup` |
| Project Files | DocumentLibrary | `3363639a-c52d-4789-b2cf-34a71ef9a793` | `/sites/EDNSystems/ProjectFiles` | on | 0 | no attachments; no unique permissions |
| Evidence & Test Results | DocumentLibrary | `0febf366-e8c8-4f43-ad33-26123fb9957d` | `/sites/EDNSystems/EvidenceTestResults` | on | 0 | no attachments; no unique permissions |
| Engineering Knowledge | DocumentLibrary | `adb9a65b-2429-4528-b9c3-04dae9d2cfc0` | `/sites/EDNSystems/EngineeringKnowledge` | on | 7 | no attachments |
| Work Evidence | DocumentLibrary | `3446d6a3-aee4-4d7a-b65a-ee2380f61ee5` | `/sites/EDNSystems/WorkEvidence` | on | 2 | unique permissions; no attachments |

The inventory also observed a separate `Engineering` library, but it is not the
V1 knowledge destination. `Evidence & Test Results` exists and is relevant, but
is empty and has the same basic library controls as `Project Files`.

## Verified Work Log schema

All observed custom Work Log columns are optional at SharePoint level. Relevant
types and relationships:

| Display name | Internal name | Type | Default/choices | Relationship |
|---|---|---|---|---|
| Project | `Project` | Text | — | legacy text; use `ProjectLookup` for V1 |
| Project Record | `ProjectLookup` | Lookup | — | Projects `Title`; indexed |
| Client | `Client` | Text | — | legacy text; use `ClientLookup` for V1 |
| Client Record | `ClientLookup` | Lookup | — | Clients `Title` |
| Work Date | `WorkDate` | DateTime | — | indexed |
| Hours | `Hours` | Number | — | map to V1 minutes |
| Work Type | `WorkType` | Choice | default `Field Work`; Administration, Design, Field Work, Remote Support, Reporting, Sales, Stand-down, Training, Travel | — |
| Technical Summary | `TechnicalSummary` | Note | — | candidate V1 summary/technical note mapping |
| Billable | `Billable` | Boolean | — | billing projection input |
| Rate Code | `RateCode` | Choice | APEX-95, Fixed Price, Non-billable, Scheduled Night-135, Stand-down-95 | existing commercial coding; requires owner treatment decision |
| Task or Job Reference | `TaskReference` | Text | — | billing/task reference |
| Related Action | `ActionLookup` | Lookup | — | Actions `Title` |
| Evidence Link | `EvidenceLink` | URL | — | reference only |
| Work Log Reference | `WorkLogReference` | Text | — | existing reference field |
| Invoice Status | `InvoiceStatus` | Choice | default `Not Ready`; Included in Invoice, Not Ready, Paid, Ready to Invoice, Written Off | indexed |
| Approval Status | `ApprovalStatus` | Choice | Approved, Draft, Invoiced, Rejected, Submitted | — |
| Invoice Number | `InvoiceNumber` | Text | — | future billing reference |

Native `ID`, `Author`, `Created`, `Editor`, `Modified` and version history are
available. No Work Capture IDs, submission keys, schema/provenance hashes,
correction fields, evidence-status fields, photo-policy fields, or engineer
field were observed.

## Relationships and dependencies

Projects has a lookup to Clients (`ClientLookup` → `Clients.Title`). Work Log
and Actions each have lookups to Projects and Clients; Work Log also looks up
Actions through `ActionLookup`. Project Files, Evidence & Test Results and
Engineering Knowledge each expose project/client metadata fields in their
library schemas. The inventory observed existing webhooks on Projects, Clients,
Actions, Project Files and Engineering Knowledge (and other EDN objects). Their
targets and payload consumers were intentionally not copied because they contain
secret-bearing endpoint tokens. Power Apps packages, Power Automate definitions,
external connector configuration, list/site permissions, content types and
Purview policy bodies were unavailable; absence is therefore **unknown**, not
evidence of absence.

Existing views confirm Work Log is already consumed by operational and finance
views (`Operations - Recent Work Log`, `Finance - All Uninvoiced Work`, and
`Finance - Ready to Invoice`). Existing project views include `Operations -
Secure Client Work`, filtering `SecurityClassification` values `Secure Client -
No Photos` and `Defence Protected`.

## Contract reconciliation

The V1 contract remains the application/event contract. Existing fields are
reused or mapped; no live schema change is implied by this review.

| V1 semantic group | Classification | Live mapping/result |
|---|---|---|
| project/client | existing field requiring mapping | `ProjectLookup`/`ClientLookup` lookups; legacy text fields must not be used as canonical IDs |
| work date/type | existing field requiring mapping | `WorkDate`, `WorkType` |
| duration | existing field requiring mapping | `Hours` converted to integer minutes |
| summary | existing field requiring mapping | `TechnicalSummary` |
| billable/task/invoice | existing field requiring mapping | `Billable`, `TaskReference`, `RateCode`, `InvoiceStatus`, `ApprovalStatus`, `InvoiceNumber` |
| action relationship | reusable existing field | `ActionLookup` to Actions |
| evidence reference | existing field requiring mapping | `EvidenceLink`; binary remains in a library |
| secure/photo profile | existing field requiring mapping | project `SecurityClassification`; no Work Log photo fields |
| engineer/person | missing field requiring later creation or controlled author mapping | `Author` is creator, not a reliable work performer |
| capture identity/provenance | missing field requiring later creation | capture ID, submission key, schema, source app, captured-at, hash, defaults, revision/correction fields |
| outcome, follow-up, evidence status/requirement, technical value | missing field requiring later creation | no equivalent Work Log fields verified |
| rate class | conflicting field requiring owner decision | current `RateCode` choices embed commercial rate labels; V1 must not hard-code rates |

Required SharePoint additions, if approved later, must be optional at the list
schema level and enforced by the capture application. Existing automations and
finance views must be regression-tested before any additive field or form change.

## Evidence destination recommendation

Use **Project Files** for V1 binary evidence references. It is empty, versioned,
has no unique permissions, and is already project-oriented with a Project/Client
metadata pattern and an observed webhook dependency. Evidence & Test Results is
also empty and versioned, but its existence does not establish a stronger
canonical ownership contract. Keep the latter available for a later specialised
test-result projection. `Work Evidence` is not recommended because it has unique
permissions and existing contents, increasing access and dependency risk.

## Smallest future test activation (not executed)

1. Owner approves a dated activation window and the exact manifest hash below.
2. Confirm the mobile operator connection can read Projects/Clients and create
   one Work Log item without bypassing existing permissions.
3. Add only the minimum optional Work Log columns for identity, performer,
   outcome, evidence state and provenance; do not alter existing billing fields.
4. Create the standalone responsive capture app and acceptance flow, with a
   retry-safe submission key and no offline queue.
5. Use Project Files for an optional evidence upload/reference path; do not write
   to Evidence & Test Results in the first test.
6. Test with one synthetic/non-production capture and one correction path only
   after a separate mutation approval; verify existing views/webhooks and then
   stop for review.

The current owner decision is **read-only review only**. The next approval must
explicitly authorize the bounded test mutation; this review does not authorize it.
