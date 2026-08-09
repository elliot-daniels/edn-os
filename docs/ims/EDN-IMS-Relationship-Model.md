# EDN IMS Relationship Model

Status: Implementation design; no deployment authorised  
Date: 2026-08-09

## Principles

- A business fact has one authoritative record. Other structures store lookups
  or durable evidence URLs, not copied facts.
- Every authoritative record receives a stable text identifier (`IMSRecordID` or
  the domain-specific ID) independent of SharePoint item ID and display name.
- SharePoint lookups provide navigable same-site references. A durable source URL
  and stable ID preserve provenance when a lookup is impractical.
- New lookups are optional during migration. Mandatory circular lookups are
  prohibited.
- Multi-value lookups are used only for bounded reference catalogues. High-volume
  many-to-many relationships should later use a mapping structure rather than
  unbounded lookup fields.
- Dashboards aggregate records but never become authoritative.

## Relationship classes

| Class | Meaning | Storage rule |
|---|---|---|
| Authoritative | Defines ownership or lifecycle | Single-value lookup where practical; stable ID retained |
| Optional reference | Adds context without owning the record | Optional lookup or evidence URL |
| Derived | Reproducible from authoritative links | Calculate at query/view/report time; do not persist unless needed for performance and labelled derived |
| Dashboard-only | Presentation grouping/count | Never written back as source data |

## Authoritative relationship matrix

| Source | Relationship | Target | Cardinality | Class | Storage owner |
|---|---|---|---|---|---|
| Project | delivered for | Client | many-to-one | Authoritative | Projects |
| Quote | offered to | Client | many-to-one | Authoritative | Quotes |
| Quote | initiates/supports | Project | many-to-one optional | Optional reference | Quotes |
| Action | assigned within | Project | many-to-one optional | Optional reference | Actions |
| Action | originates from | Risk or Event/Finding | zero-or-one source type plus stable source ID/URL | Authoritative provenance | Actions |
| Approval | decides | Any governed record | polymorphic stable ID/type/URL | Authoritative provenance | Approvals |
| Work Log | evidences | Project/Action/Control/Finding | optional bounded references | Optional evidence | Work Log |
| Engineering Knowledge | applies to | Process/Control | many-to-many bounded | Optional reference | Engineering Knowledge |
| Controlled Document | governs | Process/Control | many-to-many bounded | Authoritative document metadata | Controlled Documents |
| Obligation | applies to | Client/Project | optional bounded | Optional context | Obligations |
| Control | implements | Obligation | many-to-many | Authoritative mapping | Processes and Controls initially; mapping list if scale demands |
| Risk | affects | Project/Client/Asset/Control | optional context lookups | Optional reference | Risks and Opportunities |
| Risk | treated by | Action | derived inverse | Derived | From Actions source relationship |
| Risk | accepted by | Approval | one approval when accepted | Authoritative decision | Risks and Opportunities plus Approval ID |
| Event/Finding | concerns | Project/Client/Obligation/Control/Risk | optional lookups | Optional reference | Assurance, Events and Findings |
| Event/Finding | corrected by | Action | derived inverse | Derived | From Actions source relationship |
| Event/Finding | closed by | Approval | one approval when closure requires attestation | Authoritative decision | Event/Finding plus Approval ID |
| Executive Metric | measures | Process/Control | optional many-to-one | Optional reference | Executive Metrics |
| System Status | monitors | Process/Control | optional many-to-one | Optional reference | System Status |
| Evidence | supports | Any IMS record | stable evidence URL plus description | Authoritative provenance | Record requiring evidence |

## Stable identifiers

| Structure | Identifier field | Format example | Generation |
|---|---|---|---|
| Projects | Existing project identifier; otherwise `IMSProjectID` | `PRJ-2026-001` | Human/business rule |
| Clients | Existing client identifier; otherwise `IMSClientID` | `CLI-0001` | Human/business rule |
| Actions | `IMSActionID` | `ACT-2026-0001` | Deterministic sequence at creation |
| Approvals | `IMSApprovalID` | `APR-2026-0001` | Deterministic sequence at creation |
| Obligations | `IMSRequirementID` | `REQ-ISO9001-0001` | Human-confirmed catalogue rule |
| Processes/Controls | `IMSControlID` | `CTL-SEC-001` | Human-confirmed catalogue rule |
| Risks/Opportunities | `IMSRiskID` | `RSK-2026-0001` | Deterministic sequence at creation |
| Assurance/Events/Findings | `IMSEventID` | `AEF-2026-0001` | Deterministic sequence at creation |
| Controlled Documents | `IMSDocumentID` | `DOC-POL-001` | Human-confirmed document rule |

Identifiers are immutable after approval. Automation may propose or allocate an
unused sequence, but collision detection and a human-visible value are required.

## Provenance contract

Material IMS records use these fields where applicable:

- `IMSSourceType`: Human observation, SharePoint record, Document, Email,
  Client requirement, Standard, Legislation, System event, or AI-assisted draft;
- `IMSSourceReference`: durable URL or external reference;
- `IMSSourceRecordID`: stable identifier of the source record;
- `IMSEvidenceReference`: one or more durable evidence URLs, not copied content;
- `IMSRecordedBy` and native Created/Modified history;
- `IMSApprovalID` for decisions requiring authority; and
- `IMSAIAssistance`: None, Suggested classification, Suggested mapping, or Draft
  summary, plus human review status.

AI must not invent an evidence reference. An AI-assisted mapping remains draft
until a human confirms it.

## Dependency and deletion rules

- Lookups use restrict-delete only where loss would invalidate an active record;
  otherwise no cascade and a retained stable ID/URL are preferred.
- Deleting a referenced IMS record is prohibited once it supports an approval,
  accepted risk, closed finding or effective controlled document. Supersede or
  retire it instead.
- Renaming display names must not change internal field names, list GUIDs or URLs.
- The existing `SOPsTemplates` URL should remain stable even if navigation later
  displays “Controlled Documents”.
- Relationship deployment follows target creation: no lookup is provisioned
  until both ends exist and their stable IDs are validated.

## Dashboard-only aggregations

The following are derived views: open actions by project, residual risks by
domain, overdue control reviews, findings by severity, controlled documents due
for review, metrics outside threshold, and evidence coverage. These values must
not be written into separate dashboard lists.

## Validation rules

1. Every lookup target is in the target schema and deployed first.
2. No required lookup participates in a dependency cycle.
3. Source ID and URL survive lookup removal or display-name changes.
4. Human decisions resolve to an `Approvals` record and named person.
5. Restricted evidence is linked only when the viewer is authorised; links do
   not grant access.
6. Permission, content-type, Power Platform and Purview behaviour remains unknown
   until separately inspected and approved.

