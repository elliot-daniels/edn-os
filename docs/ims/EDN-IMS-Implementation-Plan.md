# EDN IMS Controlled SharePoint Implementation Plan

Status: Design and validation only; no deployment authorised  
Date: 2026-08-09

## 1. Target architecture and exclusions

Existing authoritative structures remain Projects, Clients, Actions, Assets,
Approvals, Executive Metrics, System Status, Work Log, Quotes and Engineering
Knowledge. Project Files, Engineering, Executive and Documents remain distinct
document stores. `SOPs & Templates` becomes the controlled-document source while
retaining its technical URL. The existing Risk Register is extended into Risks
and Opportunities.

Only three new logical catalogues are justified:

1. Obligations and Requirements;
2. Processes and Controls; and
3. Assurance, Events and Findings, with a restricted companion only if the
   approved access design requires it.

Do not create an Asset Register, separate Opportunity Register, SOP metadata
register, standards-specific registers, project risk registers, new action queue,
or dashboard data store. Existing competing empty objects are not deleted by
this plan.

## 2. Change safety baseline

The corrected discovery observed webhooks on Projects, Actions, Approvals,
Clients, Engineering Knowledge, Executive Metrics, Quotes and System Status.
It also observed webhooks on Project Files, Engineering and Documents. Treat all
as change-sensitive. Detailed flow/app definitions, content types, permissions
and Purview configuration remain unknown.

Default controls for every increment:

- export and hash a pre-change schema inventory to protected storage;
- use a test site or isolated approved test objects first;
- preserve GUIDs, URLs and existing internal names;
- add optional fields before enforcing conditional requirements;
- never remove or change the type of an existing field;
- regression-test every observed webhook before and after additive changes;
- record a named approval against the exact schema version;
- deploy with `ShouldProcess`, dry-run output, idempotence and structured logs;
- validate counts/settings without reading item/document content; and
- roll back by hiding fields/views, disabling new automation and restoring
  navigation—not deleting data-bearing fields.

No deployment tooling is created in IMS-005.

## 3. Webhook and automation impact matrix

| Structure | Observed dependency | Additive field risk | Rename risk | Prohibited | Required regression test | Rollback |
|---|---|---|---|---|---|---|
| Projects | Webhook | Low–Medium | High | Existing field deletion/type change | Create/update synthetic test item; verify webhook success and payload tolerance | Remove new fields from forms/views |
| Actions | Webhook | Low–Medium | High | Existing field deletion/type change; automated closure | Create/update without and with IMS fields; verify action workflow | Hide fields; disable only new rules |
| Approvals | Webhook | Medium | High | Automated approval or approver impersonation | Pending→human decision test; verify identity/timestamp | Disable new routing; preserve decisions |
| Clients | Webhook | Low–Medium | High | Existing field deletion/type change | Update test client; validate integrations ignore/add fields safely | Hide fields |
| Engineering Knowledge | Webhook | Medium | High | URL/internal rename | Upload/update synthetic file and metadata; verify webhook | Remove new views/fields from UI |
| Executive Metrics | Webhook | Medium | High | Overwriting authoritative values with derived state | Update metric; validate calculation/report behaviour | Disable derived calculation; hide fields |
| Quotes | Webhook | Medium | High | Existing field deletion/type change | Create/update synthetic quote; verify workflow and approval link | Hide fields; disable new rules |
| System Status | Webhook | Medium | High | Suppressing existing monitoring | Update test status; verify monitoring webhook | Disable new mapping/calculation |
| Project Files | Webhook | Medium | High | URL/internal rename | Upload/update synthetic file and project metadata | Revert views/navigation |
| Engineering | Webhook | Medium | High | URL/internal rename | Upload/update synthetic working file | Revert views/navigation |
| Documents | Webhook | Medium | High | Repurpose/rename as controlled library | Upload/update synthetic general document | Leave library role unchanged |
| SOPs & Templates | None observed | Low, but unknown definitions | Medium–High | URL/internal rename before review | Upload/version/approve synthetic document | Hide metadata/views; retain files |

“No observed webhook” is not proof of no Power Platform dependency.

## 4. Migration and backfill strategy

1. Snapshot schemas and record counts; never export item contents into Git.
2. Add optional fields and validate internal-name/type collisions.
3. Populate deterministic stable IDs only where missing; log old item ID, new ID,
   algorithm version and timestamp in protected migration evidence.
4. Leave relationship fields blank until target structures exist.
5. Run AI-assisted classification only as a separately approved offline draft.
   Store source references, model/tool version and `Needs review`; never fabricate
   mappings or evidence.
6. Have a human confirm classification, applicability, risk ratings, ownership,
   approval, reportability and sensitive-category decisions.
7. Enforce new-record conditional rules only after legacy records are reviewed.

Backfill classes are defined field-by-field in the target schema. Existing blank
records are not evidence that a value is “Not applicable”; use “Not assessed” or
blank until reviewed.

## 5. Rollback model

Safe rollback actions are: remove new columns from forms/views, restore prior
views/navigation, disable newly introduced calculations/reminders, detach new
lookups from UI, and mark new catalogue records Draft/Retired while retaining
data. Never delete a populated field to roll back.

Difficult-to-reverse changes requiring separate explicit approval include:

- changing a list/library URL or internal name;
- changing field type or deleting a field;
- enabling unique permissions or breaking inheritance;
- applying retention/record labels;
- migrating documents or list records;
- consolidating or deleting legacy lists;
- changing webhook/flow contracts; and
- enabling content approval or checkout where users/automation already operate.

## 6. Independently approvable increments

### IMS-006A — Metadata on existing authoritative structures

- **Scope:** Add collision-checked optional fields from the target schema to
  Projects, Clients, Actions, Assets, Approvals, Executive Metrics, System
  Status, Work Log, Quotes and Engineering Knowledge. Defer lookups whose targets
  do not yet exist.
- **Prerequisites:** Approved schema version; fresh protected inventory/backup;
  webhook contract/dependency review; test environment; rollback evidence.
- **Tests:** PnP dry run, idempotence, field type/internal-name checks, existing
  forms/views, CRUD of synthetic records, all relevant webhook regressions.
- **Validation:** No existing field altered; record counts unchanged; new fields
  optional and hidden from default views until accepted.
- **Rollback:** Hide new fields and restore prior views; retain data.
- **Approval/risk:** Named owner technical approval; Medium.

### IMS-006B — Native IMS views and navigation

- **Scope:** Add draft/review/overdue views using existing and 006A fields; add
  navigation labels only. No dashboard data store.
- **Prerequisites:** 006A accepted and operating terminology approved.
- **Tests:** View filters, audience/access behaviour, empty/large results, links.
- **Validation:** Views return source items and disclose no restricted metadata.
- **Rollback:** Delete only newly created views/navigation links or restore prior
  navigation; underlying records untouched.
- **Approval/risk:** Owner usability approval; Low.

### IMS-006C — Integrated Risks and Opportunities

- **Scope:** Extend existing empty Risk Register with the approved schema and
  calculations. Use a navigation label; do not delete Opportunity Register.
- **Prerequisites:** Risk scale, acceptance authority and sensitive-risk boundary
  approved; dependency and permission review complete.
- **Tests:** All 25 matrix combinations, thresholds, opportunity paths, overdue
  reviews, human acceptance gate, forbidden automated acceptance, idempotence.
- **Validation:** Accepted state impossible without valid Approval/person/date;
  source/evidence retained.
- **Rollback:** Disable calculations/reminders, hide fields/views, restore label;
  retain records.
- **Approval/risk:** Owner governance approval; Medium–High.

### IMS-006D — Controlled Documents

- **Scope:** Extend `SOPs & Templates`; keep URL/internal identity; present
  “Controlled Documents” in navigation/views. Do not repurpose Documents.
- **Prerequisites:** Document types, classification, approval authority,
  permissions and retention approved; dependency review complete.
- **Tests:** Upload/version/review/approve/supersede synthetic documents; approval
  identity; review-date views; existing links; permission boundaries.
- **Validation:** Native history retained; Approved requires human Approval;
  templates and controlled effective documents are distinguishable.
- **Rollback:** Remove new views/navigation, hide metadata, disable new routing;
  never delete files or fields.
- **Approval/risk:** Owner information-governance approval; Medium–High.

### IMS-006E — Obligations and Requirements

- **Scope:** Create the lightweight catalogue with EDN interpretations and source
  references only.
- **Prerequisites:** Initial scope, jurisdictions, authorised standards access,
  owner and review cadence approved.
- **Tests:** Stable IDs, edition changes, applicability decisions, no licensed
  text fixture, source URL validation and idempotence.
- **Validation:** Every current requirement has source/version/review owner;
  unknown applicability remains Under review.
- **Rollback:** Remove navigation and retire draft records; retain catalogue.
- **Approval/risk:** Owner plus specialist input where required; Medium.

### IMS-006F — Processes and Controls

- **Scope:** Create one typed Process/Control catalogue; no standard-specific
  control lists.
- **Prerequisites:** 006E; initial operating processes/control set approved.
- **Tests:** type choices, ownership, review dates, evidence expectations and
  requirement mappings.
- **Validation:** Each active control has owner, purpose and review date; no
  unsupported conformity or Essential Eight maturity state.
- **Rollback:** Hide navigation, retire drafts, retain records.
- **Approval/risk:** Owner; Medium.

### IMS-006G — Assurance, Events and Findings

- **Scope:** Create typed standard-access structure and, only if approved,
  restricted companion using the same schema.
- **Prerequisites:** Legal/WHS/security advice where needed; permission,
  classification, retention, reportability and closure rules approved.
- **Tests:** Each enabled type, sensitivity routing, unauthorised access denial,
  source/evidence links, action creation, closure Approval and effectiveness.
- **Validation:** Sensitive narrative cannot leak through views/notifications;
  automation cannot decide reportability or closure.
- **Rollback:** Disable intake/routing, hide navigation; preserve records under
  approved retention and access controls.
- **Approval/risk:** Owner and specialist/technical approval; High.

### IMS-006H — Relationships and lookups

- **Scope:** Add relationships from the approved relationship model after all
  targets exist; add stable source IDs/URLs before lookups.
- **Prerequisites:** 006A and relevant 006C–G structures deployed; record IDs
  validated; lookup/index capacity reviewed.
- **Tests:** valid targets, deleted/retired target behaviour, cycles, multi-value
  limits, access-restricted targets and migration reconciliation.
- **Validation:** No required cycles; no display-name matching; dashboards derive
  inverse relationships.
- **Rollback:** Remove lookups from forms/views while retaining IDs/URLs; do not
  delete populated columns.
- **Approval/risk:** Technical owner; Medium.

### IMS-006I — Permissions, classification and retention

- **Scope:** Apply separately approved access boundaries, labels and retention.
- **Prerequisites:** Complete permission/content-type/Purview discovery or admin
  design evidence; record-class schedule; legal/client/WHS/security decisions;
  test tenant.
- **Tests:** role matrix, inherited versus restricted access, search leakage,
  sharing, retention/disposition, recovery and audit history.
- **Validation:** Least privilege; authorised users retain operational access;
  backup/disposal align with classification.
- **Rollback:** Permission/retention rollback is policy-specific and may be
  irreversible; require Microsoft 365 specialist-confirmed procedure before run.
- **Approval/risk:** Named information-governance authority; High.

### IMS-006J — Dashboard and executive integration

- **Scope:** Add links/aggregations over authoritative views and management-review
  inputs; no duplicate metrics or compliance score.
- **Prerequisites:** Operating records and views stable; access trimming tested.
- **Tests:** source links, counts, thresholds, empty/error states, permissions and
  mobile usability.
- **Validation:** Every displayed number resolves to authoritative records and
  calculation provenance.
- **Rollback:** Restore previous dashboard configuration/assets.
- **Approval/risk:** Owner; Low–Medium.

## 7. Deployment approval package required for every IMS-006 increment

Each future package must contain exact script/configuration hashes, target site
and object IDs, pre/post inventory references, affected webhooks, dry-run output,
tests, backup and rollback procedure, execution window/operator, permissions,
classification, expected changes and named GO decision. An approval for one
increment does not authorise another.

## 8. Business OS product boundary

Reusable platform capability: schema/config validation, stable IDs, typed record
families, human-authority enforcement, evidence/provenance links, additive PnP
planning, drift/dependency checks, rollback, view generation and policy gates.

EDN configuration: tenant/list GUID mappings, display terminology, domain and
record-type choices, risk thresholds, classifications, authorities, retention,
document types, jurisdictions, metrics, webhook tests and navigation. Future
tenant configuration belongs in versioned validated files as described by the
policy model; secrets and live exports remain external. Multi-tenancy is out of
scope.

## 9. Remaining owner/specialist decisions

Before relevant increments, confirm:

1. named risk-acceptance authorities and escalation requirements;
2. Australian WHS jurisdiction(s) and legal/reportability obligations;
3. restricted-record architecture, roles and retention;
4. operational record classification and retention schedule;
5. initial requirement/control catalogue contents and authorised standards;
6. Essential Eight objective after a separate evidence-based assessment; and
7. whether any display-name rename is worth its usability and dependency risk.

