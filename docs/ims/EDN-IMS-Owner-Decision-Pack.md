# EDN IMS Owner Structure Decision Pack

Status: Owner review required  
Date: 2026-08-09  
Decision authority: Elliot Daniels  
Implementation authority: None

## 1. Purpose and evidence boundary

This pack converts the completed IMS-003 discovery into owner decisions about
SharePoint sources of truth. It does not authorise provisioning, migration,
consolidation, deletion, automation changes, permission changes, or any other
tenant mutation.

The evidence baseline is exclusively:

- the corrected inventory at
  `F:\EDN OS\Working\SharePoint Inventory\2026-08-07-rerun-1`;
- the corrected assessment at
  `F:\EDN OS\Working\SharePoint Gap Assessment\2026-08-07-rerun-1`;
- the approved EDN IMS architecture, discovery and gap-mapping specifications;
  and
- the completed live-discovery approval record.

The unsuccessful original inventory and first over-broad comparison are
explicitly excluded. Content types, detailed permissions, Power Platform
definitions and Purview policy bodies were unavailable and remain **unknown**,
not absent. Item contents were outside discovery scope, so apparent purposes are
inferences from object type, name, settings and architecture—not content review.

## 2. Confirmed baseline

The following recommendations stand unless later evidence materially contradicts
them.

| Disposition | Authoritative structures |
|---|---|
| Reuse unchanged | Assets; Work Log |
| Extend existing | Actions; Approvals; Clients; Engineering Knowledge; Executive Metrics; Projects; Quotes; System Status |

`Assets` is currently a document library, so “reuse unchanged” means preserve it
as the authoritative asset-document library now; it does not prove that it can
serve every future structured asset-register use case. That distinction is part
of Decision IMS-SD02 below.

## 3. Recommended resolution of the 13 owner-decision items

### IMS-SD01 — Action Register / Actions

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Actions` (GenericList, 3 items, versioning enabled, one webhook); `Action Register` (GenericList, empty, versioning enabled, no observed automation) |
| Apparent current purpose | Both appear intended to track actions; `Actions` is the operating list used by current architecture and automation |
| Relevant evidence | Exact authoritative `Actions` match; populated and webhook-connected versus empty `Action Register`; detailed permissions/content types unknown |
| Potential overlap | Functionally duplicate action registers |
| Recommended disposition | **Consolidate later** |
| Recommended authoritative source of truth | `Actions` |
| Why | It is populated, integrated, and already designated for corrective, preventive, treatment and improvement actions |
| Risks | Hidden dependencies or intended distinctions may not appear in metadata; premature deletion could remove configuration or links |
| Automation/webhook impact | Preserve the `Actions` webhook; verify references before any migration or retirement |
| Information still unknown | Item semantics, owners, views in active use, detailed permissions, content types, external links |
| Confidence | High |
| OWNER DECISION | |

### IMS-SD02 — Asset Register / Site Assets / Assets

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Assets` (DocumentLibrary, 8 items); `Asset Register` (GenericList, empty); `Site Assets` (DocumentLibrary, 18 items); all versioned, no observed automation |
| Apparent current purpose | `Assets` likely business asset documents; `Asset Register` was intended as structured inventory; `Site Assets` is the standard site-assets library used for site resources |
| Relevant evidence | `Assets` is the confirmed baseline source; `Asset Register` is empty; `Site Assets` is a library, populated, and named/located like a SharePoint site-support library |
| Potential overlap | Name overlap obscures a real distinction between asset records, asset documents and site presentation resources |
| Recommended disposition | `Site Assets`: **Out of IMS scope**. `Asset Register`: **Further investigation required**, then either retain as the structured companion to `Assets` or consolidate later |
| Recommended authoritative source of truth | `Assets` for asset documents now; one structured asset register only if operational asset records are genuinely required |
| Why | A document library cannot safely be assumed to replace a structured asset register, while `Site Assets` should not be repurposed for governance |
| Risks | Forcing structured asset data into a library would weaken reporting; creating a register without a usage need would add administration |
| Automation/webhook impact | None observed; unobserved Power Platform dependencies remain unknown |
| Information still unknown | What the eight `Assets` items represent; intended `Asset Register` schema; whether endpoint/software/service inventory is managed elsewhere; permissions/content types |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD03 — Engineering / Engineering Knowledge

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Engineering` (DocumentLibrary, 15 items, one webhook); `Engineering Knowledge` (DocumentLibrary, 7 items, one webhook); both versioned |
| Apparent current purpose | `Engineering` appears to hold working/project engineering material; `Engineering Knowledge` appears to hold approved reusable knowledge |
| Relevant evidence | Different populated libraries and URLs; both independently automated; architecture explicitly assigns the knowledge-system role to `Engineering Knowledge` |
| Potential overlap | Engineering documents may be copied between working and approved knowledge locations without a clear promotion rule |
| Recommended disposition | **Keep separate** |
| Recommended authoritative source of truth | `Engineering` for working engineering material; `Engineering Knowledge` for reviewed reusable knowledge |
| Why | Lifecycle and authority differ. A controlled promotion/link relationship is safer than merging work-in-progress with approved knowledge |
| Risks | Ambiguous promotion criteria could create duplicates or outdated knowledge |
| Automation/webhook impact | Both webhooks must be mapped before metadata or lifecycle changes |
| Information still unknown | Existing webhook behaviour, approval/promotion process, permissions, content types and document semantics |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD04 — Executive / Executive Metrics

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Executive` (DocumentLibrary, 7 items, no observed automation); `Executive Metrics` (GenericList, 4 items, one webhook); both versioned |
| Apparent current purpose | Executive documents versus structured dashboard measures |
| Relevant evidence | Different object types and populated records; dashboard architecture already names `Executive Metrics` as its metric source |
| Potential overlap | Similar names only; the record roles are complementary |
| Recommended disposition | **Keep separate** |
| Recommended authoritative source of truth | `Executive Metrics` for measures; `Executive` for executive documents and review packs |
| Why | A document library and a metrics register serve different purposes and should relate rather than merge |
| Risks | Review decisions could become buried in documents unless recorded in `Approvals` and linked |
| Automation/webhook impact | Preserve and assess the `Executive Metrics` webhook before extension |
| Information still unknown | Document lifecycle, detailed permissions, content types, and metric automation behaviour |
| Confidence | High |
| OWNER DECISION | |

### IMS-SD05 — Project Files / Project Register / Projects

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Projects` (GenericList, 3 items, one webhook); `Project Register` (GenericList, empty); `Project Files` (DocumentLibrary, empty, one webhook); all versioned |
| Apparent current purpose | `Projects` is the operational project register; `Project Register` is an unused competing register; `Project Files` is a document library intended to support project records |
| Relevant evidence | Confirmed baseline names `Projects`; it is populated and automated; competing register is empty; library differs by record type but has automation |
| Potential overlap | `Project Register` duplicates `Projects`; `Project Files` is complementary if linked to `Projects` rather than treated as a register |
| Recommended disposition | `Project Register`: **Consolidate later**. `Project Files`: **Keep separate** as the project-document system, linked to `Projects` |
| Recommended authoritative source of truth | `Projects` for project records; `Project Files` for project documents |
| Why | This preserves one structured project register while separating documents without duplicating project facts |
| Risks | Empty objects can still carry configuration; project documents may currently live elsewhere; webhook behaviour is unknown |
| Automation/webhook impact | Map both `Projects` and `Project Files` webhooks before changes; verify no references to `Project Register` before retirement |
| Information still unknown | Webhook owners/targets, intended folder/metadata model, permissions, content types, and external links |
| Confidence | High for the register; Medium for the library lifecycle |
| OWNER DECISION | |

### IMS-SD06 — Quote Register / Quotes

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Quotes` and `Quote Register`, both empty GenericLists with versioning; `Quotes` has one webhook |
| Apparent current purpose | Competing structured quote registers |
| Relevant evidence | Architecture names `Quotes`; only `Quotes` has an observed automation dependency |
| Potential overlap | Likely duplicate source-of-truth candidates |
| Recommended disposition | **Consolidate later** |
| Recommended authoritative source of truth | `Quotes` |
| Why | It matches the established architecture and automation integration; there is no evidence supporting a second register |
| Risks | Both are empty, so operational intent cannot be inferred from records; unknown integrations may exist |
| Automation/webhook impact | Preserve and understand the `Quotes` webhook before any schema change; verify `Quote Register` dependencies before retirement |
| Information still unknown | Intended workflows, permissions, content types, external references and future quote-document location |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD07 — Documents / Controlled Documents

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Documents` (DocumentLibrary, 6 items, versioning enabled, one webhook); also `SOPs & Templates` (empty versioned library) and `SOP Register` (empty versioned list) |
| Apparent current purpose | `Documents` is a general shared library; SOP structures appear intentionally aimed at governed procedures/templates |
| Relevant evidence | No exact Controlled Documents object; existing libraries are versioned; content types, permissions, retention and Purview settings are unknown |
| Potential overlap | General documents, controlled policies/SOPs and templates may be mixed or redundantly split |
| Recommended disposition | **Further investigation required**; do not designate `Documents` as Controlled Documents yet. Prefer extending `SOPs & Templates` if its intended scope matches, with `SOP Register` consolidated later unless it supplies necessary metadata not supported by the library |
| Recommended authoritative source of truth | One controlled-document library, provisionally `SOPs & Templates`; `Documents` remains general collaboration storage |
| Why | Controlled documents need an explicit lifecycle, classification, approval and retention boundary. Applying that boundary to a general shared library is disproportionate and risky |
| Risks | A separate controlled library adds navigation and governance; using `Documents` could over-control unrelated files or expose controlled material |
| Automation/webhook impact | `Documents` has a webhook; its purpose must be mapped. No automation was observed on the SOP structures |
| Information still unknown | Actual file purposes, permissions, content types, labels, retention, approval configuration, and webhook behaviour |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD08 — Obligations and Requirements

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | No exact structure; client requirements may partly reside in `Clients`, `Quotes`, projects or documents |
| Apparent current purpose | A versioned catalogue of standards, legal, contractual and internal obligations mapped to controls |
| Relevant evidence | Architecture requires framework/version provenance; corrected inventory found no deterministic duplicate; contents and content types were not inspected |
| Potential overlap | Client-specific requirements belong with clients/quotes, but reusable obligations need one cross-business catalogue |
| Recommended disposition | **Create new**, only after the owner approves IMS scope and confirms no operational catalogue exists elsewhere |
| Recommended authoritative source of truth | `Obligations and Requirements` catalogue; `Clients`, `Quotes` and `Projects` retain contextual links, not duplicate requirement text |
| Why | Requirements are many-to-many, versioned reference records and do not fit safely inside a client, quote or document record |
| Risks | Maintenance burden and accidental copying of licensed standards text |
| Automation/webhook impact | New automation should initially be limited to review reminders; human applicability decisions remain authoritative |
| Information still unknown | Applicable jurisdictions, standards access, client obligations, review ownership and retention |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD09 — Processes and Controls

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | No exact structure; `SOP Register`, `SOPs & Templates`, `System Status` and `Engineering Knowledge` are related but not equivalent |
| Apparent current purpose | Stable catalogue of business processes and controls, their owners, operation, evidence expectations and requirement mappings |
| Relevant evidence | No deterministic duplicate; SOP objects are empty and document-oriented; `System Status` is operational monitoring, not the control definition itself |
| Potential overlap | Procedures describe how controls operate; system status records checks; neither should become the control catalogue |
| Recommended disposition | **Create new** as a lightweight combined process/control catalogue |
| Recommended authoritative source of truth | `Processes and Controls`, linked to controlled procedures, assets, requirements, risks, metrics and evidence |
| Why | Controls need reusable many-to-many mappings and lifecycle fields that do not belong in document or monitoring records |
| Risks | Over-documentation for a one-person business; controls may become paperwork rather than operating routines |
| Automation/webhook impact | Begin without approval automation; add reminders/evidence prompts only after the manual operating model works |
| Information still unknown | Initial control scope, owners/frequencies, Essential Eight target and evidence expectations |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD10 — Risks and Opportunities / Risk Register / Opportunity Register

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Risk Register` and `Opportunity Register`, both empty versioned GenericLists with no observed automation |
| Apparent current purpose | Separate registers for threats and opportunities |
| Relevant evidence | Exact semantic candidates already exist; both are empty; architecture proposes one typed integrated model; permissions/content types unknown |
| Potential overlap | Two sources would duplicate ownership, assessment, treatment and review mechanics |
| Recommended disposition | **Consolidate later** into one authoritative typed structure by extending and renaming one existing list; do not create a third list |
| Recommended authoritative source of truth | Prefer `Risk Register`, extended to `Risks and Opportunities`; retire or redirect `Opportunity Register` only after dependency checks |
| Why | Risk and opportunity share context, ownership, actions and reviews; one list supports domain-specific views without duplicate governance |
| Risks | WHS/security sensitivity may require restricted storage or separate permission boundaries; scoring and acceptance authority are unapproved |
| Automation/webhook impact | None observed, but Power Platform definitions were unavailable; verify dependencies before rename/consolidation |
| Information still unknown | Risk method, acceptance authority, sensitive-record design, actual external references and legal scope |
| Confidence | High on reuse; Medium on the final access model |
| OWNER DECISION | |

### IMS-SD11 — Assurance, Events and Findings

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | No exact structure; `Actions`, Work Log and project/engineering evidence are related but not equivalent |
| Apparent current purpose | Typed records for audits, reviews, complaints, nonconformities, hazards, incidents, security events and findings |
| Relevant evidence | No deterministic duplicate; existing `Actions` is the treatment queue, not the source event/finding record |
| Potential overlap | Findings can generate actions, but merging both destroys source, investigation and effectiveness context |
| Recommended disposition | **Create new**, initially with only the record types EDN actually uses |
| Recommended authoritative source of truth | `Assurance, Events and Findings`; `Actions` remains the authoritative follow-up queue and `Approvals` the decision ledger |
| Why | Source events and findings have distinct provenance, triage, investigation and closure needs |
| Risks | Sensitive WHS/security/personnel data may be unsafe in a mixed list; too many unused record types would overengineer the system |
| Automation/webhook impact | Defer workflow until permissions and reporting obligations are approved; automation must not decide reportability or closure |
| Information still unknown | Jurisdiction, reportability rules, sensitive access/retention design, initial record types and specialist advice |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD12 — Opportunity Register

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `Opportunity Register` (empty versioned GenericList, no observed automation) |
| Apparent current purpose | Standalone improvement/business opportunity tracking |
| Relevant evidence | Empty semantic candidate for the proposed integrated Risks and Opportunities model |
| Potential overlap | Duplicates common fields and workflow of risk/opportunity governance and may overlap commercial opportunities elsewhere |
| Recommended disposition | **Consolidate later** for IMS risks/opportunities; keep commercial sales opportunities out of IMS unless explicitly scoped |
| Recommended authoritative source of truth | Integrated `Risks and Opportunities` for IMS opportunities; the commercial system for sales opportunities |
| Why | The word “opportunity” has two business meanings that should not be conflated |
| Risks | Migration could misclassify sales pipeline records if they are later added |
| Automation/webhook impact | None observed; Power Platform definitions remain unknown |
| Information still unknown | Intended business versus IMS scope and external links |
| Confidence | Medium |
| OWNER DECISION | |

### IMS-SD13 — SOP Register / SOPs & Templates

| Attribute | Assessment |
|---|---|
| Existing SharePoint objects | `SOP Register` (empty versioned GenericList); `SOPs & Templates` (empty versioned DocumentLibrary); no observed automation |
| Apparent current purpose | Metadata register plus storage library for procedures and templates |
| Relevant evidence | Both are empty; native library metadata and version history can usually hold the document-control record without a parallel list; content types/labels/permissions unknown |
| Potential overlap | A separate register can duplicate document title, owner, version, status and review date |
| Recommended disposition | `SOPs & Templates`: **Extend existing** as the provisional Controlled Documents library. `SOP Register`: **Consolidate later** unless a tested requirement cannot be represented by library metadata/views |
| Recommended authoritative source of truth | The controlled document itself and metadata in `SOPs & Templates`; `Approvals` records human approval |
| Why | Native library metadata avoids a fragile two-record synchronization problem |
| Risks | The library name may be too narrow for policies/plans; templates may need a distinct lifecycle; permission and retention design is unknown |
| Automation/webhook impact | None observed; add review reminders/approval routing only after schema and authority are approved |
| Information still unknown | Required document types, naming decision, permissions, content types, labels, retention and approval workflow |
| Confidence | Medium |
| OWNER DECISION | |

## 4. Decisions that genuinely require owner judgment

Most source-of-truth recommendations follow from the evidence. The owner needs to
decide only these five governance questions before schema design:

1. **Structured asset scope:** Is EDN managing structured information/software/
   service/physical asset records in SharePoint, or only asset documents? This
   determines whether `Asset Register` is needed beside `Assets`.
2. **Controlled-document boundary and name:** Approve `SOPs & Templates` as the
   controlled library (potentially renamed to `Controlled Documents`) and keep
   `Documents` as general collaboration storage, or nominate another boundary.
3. **Risk method and authority:** Approve the risk/opportunity scope, scoring
   scale, review frequency and who can accept residual risk.
4. **Sensitive records:** Decide whether WHS, security, personnel and client
   events require a separately permissioned structure; detailed live permissions
   remain unknown and need a separately approved read-only review.
5. **Initial IMS scope:** Confirm the jurisdictions, standards/contractual
   obligations, Essential Eight target hypothesis and event types that EDN will
   operate first. This controls how small the new catalogues can remain.

Approving this pack does not approve fields, permissions or provisioning.

## 5. Proposed target SharePoint information architecture

### Operational registers

| Name | Purpose and system-of-record role | Status | IMS role | Key relationships |
|---|---|---|---|---|
| Projects | Authoritative project records | Existing; extend | Scope/context | Clients, risks, controls, actions, files, findings, quotes |
| Clients | Authoritative client records | Existing; extend | Interested parties and client requirements | Projects, quotes, obligations, classification |
| Actions | One action queue | Existing; extend | Treatment, corrective action and improvement | Risks, findings, approvals, projects |
| Assets | Authoritative asset-document library now | Existing; preserve | Asset evidence | Structured asset records if approved, controls, risks |
| Asset Register | Structured asset inventory only if approved | Existing candidate | Applicability, criticality and ownership | Assets, projects, controls, risks |
| Quotes | Authoritative quote register | Existing; extend | Contract/requirement review evidence | Clients, projects, risks, approvals |
| Work Log | Authoritative work evidence | Existing; reuse | Control/action evidence by reference | Projects, actions, controls, findings |
| Risks and Opportunities | Integrated typed risk/opportunity register | Extend/rename existing Risk Register | Enterprise risk model | Controls, actions, approvals, projects, assets, clients |
| Assurance, Events and Findings | Source events, assessments and findings | Proposed | Assurance and improvement source | Controls, risks, actions, approvals, evidence |

### Document libraries

| Name | Purpose and system-of-record role | Status | IMS role | Key relationships |
|---|---|---|---|---|
| Documents | General collaboration documents | Existing; keep separate | Evidence only when linked | Projects, decisions, records |
| Controlled Documents | Approved policies, procedures, plans and templates | Extend/rename `SOPs & Templates`, subject to approval | Controlled documented information | Processes, controls, requirements, approvals |
| Project Files | Project documents | Existing; keep separate | Project evidence | Projects |
| Engineering | Working engineering material | Existing; keep separate | Working evidence | Projects, Engineering Knowledge |
| Engineering Knowledge | Reviewed reusable technical knowledge | Existing; extend | Approved knowledge/reference | Controls, projects, provenance |
| Executive | Executive documents and review packs | Existing; keep separate | Management-review evidence | Metrics, approvals, actions |

### Reference and knowledge structures

| Name | Purpose and system-of-record role | Status | IMS role | Key relationships |
|---|---|---|---|---|
| Obligations and Requirements | Versioned source catalogue for applicable requirements | Proposed | Standards/legal/contract mapping | Clients, projects, processes, controls |
| Processes and Controls | Definitions of how EDN works and treats risk | Proposed | Integrated control catalogue | Requirements, risks, assets, documents, evidence, metrics |

### Governance structures

| Name | Purpose and system-of-record role | Status | IMS role | Key relationships |
|---|---|---|---|---|
| Approvals | Human decision and attestation ledger | Existing; extend | Approval, acceptance, exception and closure authority | Documents, risks, findings, quotes |
| Executive Metrics | Authoritative objectives and measures | Existing; extend | Performance evaluation | Processes, controls, management review |
| System Status | Operational service/control monitoring | Existing; extend | Monitoring evidence and exceptions | Controls, assets, findings |

### Dashboards and views

Dashboards remain consumers, never parallel sources of truth. Native SharePoint
views should first provide overdue actions, risks due for review, controls due,
open findings, document reviews due, objectives/metrics and management-review
inputs. The existing Executive Dashboard should be extended only after the
underlying records and operating routines are stable.

## 6. Minimum safe implementation sequence

1. Record owner decisions on this pack and resolve IMS scope, risk method,
   sensitive-record boundary and controlled-document boundary.
2. Perform a separately approved, read-only dependency review for the affected
   webhooks, permissions, content types, Power Platform references and Purview
   configuration. Unknown evidence must not be converted into defaults.
3. Produce a versioned field-level schema and rollback plan for existing
   authoritative structures only: Projects, Clients, Actions, Assets/Asset
   Register if approved, Approvals, Executive Metrics, System Status, Work Log,
   Quotes and Engineering Knowledge.
4. Add the minimum metadata to a test site or isolated test objects. Prefer
   optional fields initially; preserve IDs, URLs and existing automation.
5. Add native views and validate the one-person operating routines before adding
   workflows or custom forms.
6. Add tested lookups/relationships incrementally, avoiding circular mandatory
   dependencies and duplicate text fields.
7. Review automation impacts, then explicitly approve any webhook/flow changes.
8. Approve and test permissions, information classification and retention before
   sensitive records or controlled documents are introduced.
9. Extend/rename the selected existing structures for Risks and Opportunities
   and Controlled Documents. Migrate or retire empty competing structures only
   with dependency, backup and rollback evidence.
10. Create only the three genuinely new lightweight catalogues—Obligations and
    Requirements, Processes and Controls, and Assurance, Events and Findings—
    after their minimum operating use cases are approved.
11. Add dashboards last, using authoritative list/library views and links.

## 7. Product architecture check

### EDN-specific configuration

- structure display names and EDN terminology;
- applicable jurisdictions, frameworks, client obligations and IMS scope;
- risk matrices, acceptance thresholds and approval authorities;
- classifications, retention periods and restricted-record boundaries;
- workflow routing, review frequencies, metrics, targets and dashboard layout;
- mapping of EDN's existing lists, libraries, URLs, fields and webhooks; and
- Essential Eight target and evidence profile.

### Reusable Business OS platform capability

- a configurable structure registry and source-of-truth mapping;
- typed requirements, controls, risks, events/findings, actions and approvals;
- configurable metadata schemas, relationships, views and terminology;
- provenance/evidence links and immutable approval attribution;
- human-authority workflow gates;
- classification, retention, backup and output-location policy rules;
- read-only discovery, deterministic comparison, drift detection and rollback;
- automation dependency inventory and change-impact gates; and
- metrics/dashboard projections over authoritative records.

Reusable code must consume configuration for names, IDs, record types,
classifications, authorities, scales and workflows. It must not hard-code EDN's
terms, standards scope or one-person approval model.

## 8. Policy defaults worth encoding later

These established controls should become machine-readable policy only after the
policy model is designed:

| Policy area | Established default |
|---|---|
| Discovery classification | `EDN Confidential` for live inventories, reports and backups |
| Retention | 12 months, then disposal only after implementation decisions and required audit/troubleshooting are complete |
| Backup | Required; same classification, retention and disposal trigger as primary output; hash manifest and zero-mismatch verification |
| Git exclusion | Live inventory and generated assessment never enter Git |
| Discovery mode | Metadata-only, read-only, explicit site boundary, approved delegated permission and interactive MFA |
| Approval authority | Named human approval before authentication; humans remain authoritative for risk acceptance, approvals, closure and exceptions |
| Output | Explicit protected path outside Git; no-clobber; separate primary, backup and assessment paths |
| Unknown handling | Permission/API failures and unavailable sections remain visible and are never interpreted as absence |
| Secrets/content | No credentials, tokens, headers, file contents, item values, email bodies or stack traces in output |
| Change gate | No provisioning from discovery recommendations; field schema, dependencies, permissions, retention, test deployment and rollback require approval |
| Provenance | Record script/schema versions, timestamps, source fingerprint and hashes |

## 9. Owner approval block

The owner may approve this pack with explicit exceptions rather than responding
to thirteen separate questions.

| Decision | Owner response |
|---|---|
| Approve recommended dispositions IMS-SD01 through IMS-SD13, subject to recorded exceptions | |
| Structured asset scope | |
| Controlled-document boundary/name | |
| Risk method and acceptance authority | |
| Sensitive-record storage boundary | |
| Initial IMS scope | |
| Exceptions or conditions | |
| Decision: Approve / Conditional / Reject | |
| Approver and date | |

