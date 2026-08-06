# EDN IMS Staged Implementation Backlog

Status: Proposed; no tenant changes authorised  
Date: 2026-08-05  
Delivery principle: smallest useful integrated system, evidence before dashboards

## 1. Backlog rules

- Work is organised by enduring business capability, not by ISO standard or
  development sprint.
- A task is complete only when its decision/evidence is recorded; document
  creation alone is not operating effectiveness.
- Native SharePoint lists, libraries, views and forms are preferred initially.
- Existing sources of truth are extended before new lists are approved.
- Human approval gates remain for policies, risk acceptance, exceptions and
  finding closure.
- No task in Stage 0 authorises provisioning or live-tenant modification.
- ISO requirement summaries must be checked against lawfully obtained standards.

Size guide: S = hours, M = one to two focused days, L = several days and/or
external input. Sizes are planning aids, not module boundaries.

## 2. Stage 0 — Discover and decide

Outcome: evidence-backed implementation design with no duplicate registers.

| ID | Task | Size | Dependencies | Completion evidence |
|---|---|---:|---|---|
| IMS-001 | Export a read-only inventory of live SharePoint lists, libraries, content types, fields, views, flows, permissions and retention settings | M | Owner authorises read-only tenant discovery | Timestamped inventory with tenant/site IDs and no secrets |
| IMS-002 | Locate and add or reference Installer v1.6 source and its release/handoff documentation | S | Repository/source access | Source provenance recorded; schema ownership understood |
| IMS-003 | Reconcile live structures with Projects, Clients, Actions, Assets, Approvals, Executive Metrics, System Status, Work Log, Quotes and Engineering Knowledge | M | IMS-001, IMS-002 | Reuse/extend/retire matrix with field-level evidence |
| IMS-004 | Approve EDN IMS scope, organisational boundary, locations, services and exclusions | M | Owner input | Approved scope decision linked from Decision Log |
| IMS-005 | Identify interested parties and material legal, regulatory, contractual and client requirements | M | IMS-004; legal advice where needed | Initial obligation source list with owners and review dates |
| IMS-006 | Approve information classification, sensitivity, retention and access principles | M | IMS-001, client obligations | Permission/retention decision including WHS and security records |
| IMS-007 | Approve integrated risk method: scales, criteria, appetite, treatment and acceptance authority | M | IMS-004–006 | Worked examples across delivery, WHS and security |
| IMS-008 | Determine Essential Eight scope and provisional target maturity from assets, threats and contracts | M | IMS-001, IMS-005, IMS-007 | Target decision or documented deferral; no maturity claim |
| IMS-009 | Obtain authorised copies/access for applicable standards and assign edition review responsibility | S | Commercial decision | Source references recorded without copying licensed text |
| IMS-010 | Approve the target list/library/content-type design and migration approach | M | IMS-001–009 | Owner-approved schema specification and rollback plan |

### Stage 0 exit criteria

- No authoritative structure remains undiscovered.
- Proposed additions do not duplicate a live list or library.
- IMS scope, access model and risk method are approved.
- Essential Eight target is approved or explicitly deferred.
- Provisioning plan includes backup/export, test site, validation and rollback.

## 3. Stage 1 — Establish the integrated foundation

Outcome: one minimal integrated information model operating in a non-production
test site before production deployment.

| ID | Task | Size | Dependencies | Completion evidence |
|---|---|---:|---|---|
| IMS-101 | Define stable IMS IDs and shared fields: owner, status, source, review, approval and classification | M | IMS-010 | Versioned schema contract and validation tests |
| IMS-102 | Extend Actions for corrective, treatment and improvement work | M | IMS-101 | Existing actions preserved; source/effectiveness fields tested |
| IMS-103 | Extend Approvals for policy, risk, exception and closure decisions | M | IMS-101 | Human decision/rationale/expiry history demonstrated |
| IMS-104 | Extend Assets, Clients, Projects, Executive Metrics and System Status only with approved fields | L | IMS-003, IMS-101 | No duplicate lists; existing views and dashboard remain functional |
| IMS-105 | Provision Obligations and Requirements catalogue in test site | M | IMS-009–010, IMS-101 | Versioned source, applicability and owner records demonstrated |
| IMS-106 | Provision Processes and Controls catalogue in test site | M | IMS-105 | Requirement mappings and evidence expectations demonstrated |
| IMS-107 | Provision integrated Risks and Opportunities in test site | L | IMS-007, IMS-101 | Inherent/residual assessment, owner, treatment and acceptance demonstrated |
| IMS-108 | Provision Assurance, Events and Findings with type-specific views | L | IMS-006, IMS-101 | Quality/WHS/security examples use one model with suitable access |
| IMS-109 | Provision Controlled Documents library and lifecycle | L | IMS-006, IMS-101, IMS-103 | Draft, approve, issue, review and supersede test completed |
| IMS-110 | Implement source-reference content type or link contract | M | IMS-101 | Links resolve to original list items/documents and retain version/provenance |
| IMS-111 | Add automated schema verification and idempotent deployment | L | IMS-102–110 | Dry run, repeat run and drift report pass in test site |
| IMS-112 | Perform test-site access, version-history, recovery and audit-history validation | M | IMS-111 | Test report and owner acceptance |

### Stage 1 exit criteria

- A single risk can link to a Project, Client, Asset, requirement, control, Action
  and Approval without duplicating any of them.
- A finding can resolve to its original evidence and effectiveness check.
- Sensitive records are protected according to the approved access model.
- Deployment is idempotent, testable and reversible.

## 4. Stage 2 — Operate the essential routines

Outcome: EDN performs a small number of repeatable quality, WHS and security
routines and accumulates trustworthy evidence.

| ID | Task | Size | Dependencies | Completion evidence |
|---|---|---:|---|---|
| IMS-201 | Approve integrated policy and measurable objectives | M | Stage 1 | Controlled policy, Approval and linked metrics |
| IMS-202 | Define client enquiry/quote/contract review and change-control process | M | IMS-201 | Two representative records traced from requirement to delivery |
| IMS-203 | Define engineering delivery, review, verification, acceptance and nonconforming-output controls | L | IMS-202 | Project evidence demonstrates process operation |
| IMS-204 | Define supplier/contractor selection and monitoring proportionately | M | IMS-005, IMS-201 | Material suppliers assessed; low-risk suppliers not over-administered |
| IMS-205 | Implement project/task hazard identification and WHS event workflow | L | IMS-006–008, IMS-108 | Hazard, control, consultation and closure scenario tested |
| IMS-206 | Define emergency scenarios and perform first proportionate exercise | M | IMS-205 | Exercise result, findings and Actions |
| IMS-207 | Complete information/asset inventory and ownership review | L | IMS-104, IMS-201 | Material information, systems, services and dependencies covered |
| IMS-208 | Perform initial information-security risk assessment and treatment planning | L | IMS-207 | Risks, controls, Actions and acceptance decisions linked |
| IMS-209 | Complete evidence-based Essential Eight baseline across all eight strategies | L | IMS-008, IMS-207 | Requirement-level results, evidence, exceptions and compensating controls |
| IMS-210 | Establish incident response and security event workflow | M | IMS-108, IMS-207 | Tabletop scenario and lessons recorded |
| IMS-211 | Establish controlled document review and awareness routine | S | IMS-109, IMS-201 | Review reminders and evidence of current document availability |
| IMS-212 | Establish competency evidence for material engineering/WHS/security work | M | IMS-005, IMS-201 | Role/task requirements linked to current evidence |

### Stage 2 exit criteria

- Core service delivery, WHS and information-security risks are assessed and
  treated through operating records.
- Essential Eight baseline is evidence-based, with no unsupported maturity claim.
- At least one incident/exercise and one nonconformity scenario have been tested.
- Policies and procedures are current, approved and usable.

## 5. Stage 3 — Assurance, review and improvement

Outcome: EDN can demonstrate that the integrated system is operating and improving.

| ID | Task | Size | Dependencies | Completion evidence |
|---|---|---:|---|---|
| IMS-301 | Define a risk-based annual assurance plan | M | Stage 2 | Scope covers high-risk processes/controls without auditing everything annually |
| IMS-302 | Run first integrated internal audit/control assessment | L | IMS-301 | Evidence, findings, Actions and independence consideration recorded |
| IMS-303 | Implement objective/control metrics in Executive Metrics | M | Stage 2 | Each metric has owner, source calculation, threshold and review cadence |
| IMS-304 | Add IMS exceptions and due items to Executive Dashboard | M | IMS-303 | Dashboard links only to authoritative views; no static scores |
| IMS-305 | Conduct first integrated management review | M | IMS-302–303 | Decisions cover context, risks, objectives, performance, incidents, resources and improvements |
| IMS-306 | Verify corrective-action effectiveness and close findings | M | IMS-302, IMS-305 | Human closure approvals and evidence |
| IMS-307 | Review Essential Eight target and uplift plan | M | IMS-209, IMS-305 | Balanced plan across all eight strategies |
| IMS-308 | Perform access, retention, provenance and automation health review | M | IMS-112, operating evidence | Exceptions assigned and System Status updated |

### Stage 3 exit criteria

- Internal assurance and management review operate from source-linked evidence.
- Findings are closed only after an effectiveness check.
- Dashboard metrics reconcile to authoritative data.
- System health includes IMS automation and data-quality checks.

## 6. Stage 4 — Certification-readiness and future frameworks

Outcome: EDN makes an informed commercial decision about external assurance and
future framework scope.

| ID | Task | Size | Dependencies | Completion evidence |
|---|---|---:|---|---|
| IMS-401 | Perform clause/control readiness assessment against authorised standard editions | L | Stage 3 | Traceable gaps and evidence, independently reviewed where practical |
| IMS-402 | Assess whether certification creates commercial value | M | IMS-401 | Cost, client demand, scope and timing decision |
| IMS-403 | If justified, commission independent pre-assessment | L | IMS-402 approval | External report and treatment plan |
| IMS-404 | Add ISO 14001 requirement mappings and environmental aspects only when business context warrants | M/L | Environmental scope decision | Existing core records reused |
| IMS-405 | Add ISO 22301 mappings, BIA and recovery objectives when continuity exposure warrants | M/L | Continuity scope decision | Existing assets, risks, controls and exercises reused |
| IMS-406 | Add DISP mappings only after eligibility/business case and specialist advice | L | Defence opportunity and owner approval | No unsupported DISP readiness claim |

## 7. Deferred by design

The following are intentionally not first-phase work:

- custom Power Apps for every IMS process;
- a compliance percentage or certification-readiness score;
- separate registers by standard;
- automatic ingestion of licensed standards text;
- autonomous AI decisions;
- Power BI before source data and metric definitions stabilise;
- live tenant provisioning before Stage 0 approval;
- ISO 14001, ISO 22301 or DISP implementation without a business trigger.

## 8. Exact recommended next implementation step

Implement **IMS-001: a read-only SharePoint discovery export specification and
script**, not the IMS lists.

The next change should add:

1. `Documentation/EDN-SharePoint-Discovery-Specification.md` defining the exact
   metadata to collect, sensitivity exclusions and evidence format;
2. `Installer/Export-EDNSharePointInventory.ps1` using PnP.PowerShell read-only
   commands to export lists, libraries, fields, content types, views, flows or
   flow references, permissions, versioning and retention-relevant settings;
3. synthetic/offline tests for schema normalisation and secret exclusion;
4. no tenant write commands and no execution against the live tenant until the
   owner separately authorises the read-only discovery run.

This is the smallest step that materially reduces the risk of building duplicate
registers or breaking the existing bootstrap model.
