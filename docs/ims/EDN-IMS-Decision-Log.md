# EDN IMS Decision Log

Status: Architecture decision record  
Date established: 2026-08-05  
Authority: Owner decisions override proposed recommendations

## 1. Status definitions

- **Constraint** — directed by the owner in the Module brief.
- **Proposed** — recommended architecture requiring owner approval before build.
- **Deferred** — deliberately postponed until an evidence/business trigger.
- **Open** — unresolved and potentially architecture-affecting.

No entry in this document records a live SharePoint change or certification claim.

## 2. Decisions and proposals

| ID | Status | Decision | Rationale | Consequence/evidence |
|---|---|---|---|---|
| IMS-D001 | Constraint | EDN Systems OS remains the overarching business operating system | Prevents a parallel compliance product | EDN IMS is documented as an integrated capability, not a new portal |
| IMS-D002 | Constraint | SharePoint remains the current operational database and UI | Matches the current operating model | Local modules supplement search/memory but do not become approval authority |
| IMS-D003 | Constraint | No live SharePoint provisioning occurs in this phase | Architecture and discovery precede mutation | This change creates documentation only |
| IMS-D004 | Constraint | Humans remain authoritative for approvals and decisions | Accountability cannot be delegated to automation | AI may suggest; Approvals record human decisions |
| IMS-D005 | Constraint | Standards and sprints are not permanent module boundaries | Standards overlap and change; business capabilities endure | Requirements are mappings to shared processes and controls |
| IMS-D006 | Proposed | Use one integrated Obligations and Requirements catalogue | One requirement may arise from a standard, law, contract or internal decision | Framework and edition are attributes, not separate registers |
| IMS-D007 | Proposed | Use one Processes and Controls catalogue | Controls commonly satisfy multiple quality, WHS, security and client requirements | Enables ISO/IEC 27001 applicability and Essential Eight views without duplicate controls |
| IMS-D008 | Proposed | Use one Risks and Opportunities model | Project, WHS, security and commercial risks need consistent ownership/treatment | Domain and context fields create views; separate risk registers are avoided |
| IMS-D009 | Proposed | Use one Assurance, Events and Findings record family with typed views | Audits, complaints, incidents, hazards and nonconformities share provenance/action/closure needs | Sensitive types may require permission separation without duplicating the data model |
| IMS-D010 | Proposed | Reuse Actions for corrective action, treatment and improvement | A second action tracker would fragment accountability | Extend source, type, effectiveness and closure metadata |
| IMS-D011 | Proposed | Reuse Approvals for policy, risk, exception and closure decisions | Preserves one human-authority ledger | Add typed decision, rationale, expiry and source references |
| IMS-D012 | Proposed | Reuse Projects, Clients, Assets, Executive Metrics and System Status | These are owner-stated operational sources of truth | Final fields depend on live schema discovery |
| IMS-D013 | Proposed | Add a Controlled Documents library, distinct from evidence at source | Controlled policies/procedures need version and approval lifecycle | Evidence is linked, not copied into the library |
| IMS-D014 | Proposed | Preserve evidence through stable source references and explicit relationships | SharePoint version history alone does not explain why a decision was made | Each material record carries owner, source, status, review and decision metadata |
| IMS-D015 | Proposed | Use native SharePoint forms/views before Power Apps | Proportional for one person and reduces maintenance | Custom forms require demonstrated usability or control need |
| IMS-D016 | Proposed | Build data and operating routines before IMS dashboard tiles | Dashboards cannot substitute for controls or evidence | Executive Dashboard remains unchanged until Stage 3 |
| IMS-D017 | Proposed | Adopt page-level atomic/idempotent deployment and drift checks for future schema code | Existing dashboard deployment establishes a repeatable pattern | Test site, dry run and rollback are mandatory before production |
| IMS-D018 | Proposed | Treat Essential Eight Maturity Level One as an assessment hypothesis only | ASD notes it may suit SMEs, but target must reflect threats, assets and contracts | No current maturity claim; assess all eight strategies consistently |
| IMS-D019 | Proposed | Version standards and mappings independently from operational records | ISO 9001 and ISO 45001 are under revision | Framework edition, source and review date are required fields |
| IMS-D020 | Proposed | Keep licensed standards text outside the repository | Copyright/licensing and change-control risk | Store EDN summaries and references; validate against authorised copies |
| IMS-D021 | Proposed | Use concise owner review records rather than meeting theatre | EDN is a one-person business | Management review still records inputs, decisions and actions |
| IMS-D022 | Proposed | First implementation step is read-only tenant discovery | Installer v1.6 and live schemas are missing from repository evidence | Prevents duplicate lists and unsafe assumptions |
| IMS-D023 | Deferred | Certification decision | Certification readiness is the objective; commercial value is unknown | Decide after operating evidence and readiness assessment |
| IMS-D024 | Deferred | ISO 14001, ISO 22301 and DISP domain implementation | The shared core can support them, but no immediate trigger is evidenced | Add mappings/capabilities only after scope/business decision |

## 2.1 Approved owner decisions — IMS-005

The following decisions were approved by Elliot Daniels on 2026-08-09 for
implementation design. They supersede conflicting proposals but do not authorise
live deployment.

| ID | Date | Status | Decision | Rationale | Implementation consequence | Owner/authority |
|---|---|---|---|---|---|---|
| IMS-D025 | 2026-08-09 | **Approved** | Keep the existing `Assets` library authoritative for now; create no separate structured asset register without a demonstrated operational need | Avoids an unused parallel register while preserving the current source | Design only minimal useful library metadata; leave `Asset Register` unused and do not migrate/delete it in IMS-005 | Elliot Daniels, Owner |
| IMS-D026 | 2026-08-09 | **Approved** | Use `SOPs & Templates` as the controlled-document source | Native library metadata/versioning avoids a duplicate document register | Extend the existing library; retain its technical URL/internal identity unless a dependency review proves a display-name change safe | Elliot Daniels, Owner |
| IMS-D027 | 2026-08-09 | **Approved** | Use one integrated Risks and Opportunities register with a simple likelihood × consequence method and human-only acceptance | One proportionate model prevents fragmented risk registers and automated authority | Extend the existing Risk Register; calculations may be automated, but acceptance requires a named human decision and date | Elliot Daniels, Owner |
| IMS-D028 | 2026-08-09 | **Approved** | Use one typed Assurance, Events and Findings model where practical, with maintainable isolation for sensitive records | Shared provenance/action mechanics should not force all sensitive categories into one permission boundary | Design a common schema and a restricted companion structure when required; do not default to per-item permissions | Elliot Daniels, Owner |
| IMS-D029 | 2026-08-09 | **Approved** | Initial IMS scope is EDN Systems' actual Australian quality, WHS, information-security, delivery, commercial/client and assurance environment; Essential Eight maturity and specific legal applicability require separate confirmation | Grounds the IMS in current operations without unsupported conformity or maturity claims | Make jurisdictions, frameworks and targets configurable; label unevidenced legal/Purview/permission facts unknown | Elliot Daniels, Owner |

## 3. Current-state findings that constrain decisions

| Finding ID | Classification | Finding | Source |
|---|---|---|---|
| IMS-F001 | Discovered fact | Repository has no commits and all current files are untracked | Local Git inspection on 2026-08-05 |
| IMS-F002 | Discovered fact | Current package contains ten artifacts focused on Executive Dashboard v2.2 | Repository inventory |
| IMS-F003 | Discovered fact | Dashboard links to authoritative SharePoint list views rather than maintaining a separate reporting model | `Documentation/Executive-Dashboard-v2.2.md` |
| IMS-F004 | Discovered fact | Installer v1.6 is referenced but absent | `README.md` and repository inventory |
| IMS-F005 | Discovered fact | Projects, Actions, Work Log, Quotes, Approvals and Engineering Knowledge are referenced by configuration | `SharePoint/dashboard.config.json` |
| IMS-F006 | Discovered fact | Executive Metrics and System Status are referenced by dashboard deployment code | `Installer/Deploy-ExecutiveDashboard.ps1` |
| IMS-F007 | Owner-stated fact | Clients and Assets should be reused where practical | EDN IMS brief |
| IMS-F008 | Assumption requiring validation | Live structures exist substantially as named and are authoritative | Must be tested through IMS-001 discovery |

## 4. Open decisions

| ID | Decision required | Why it matters | Required input | Decision owner |
|---|---|---|---|---|
| IMS-O001 | Exact IMS scope and exclusions | Sets all requirement and assurance boundaries | Services, locations, workers/contractors, systems and client commitments | Owner |
| IMS-O002 | Live SharePoint schema and data ownership | Determines reuse and migration design | Read-only tenant inventory and Installer v1.6 | Owner/technical review |
| IMS-O003 | Risk likelihood/consequence scales and acceptance authority | Prevents inconsistent ratings and self-approval theatre | Business, WHS, security and contractual context | Owner; specialist input as needed |
| IMS-O004 | Sensitive-record access and retention | WHS/security/client records may need restricted storage | Privacy, WHS, contractual and Microsoft 365 configuration advice | Owner/legal or specialist advice |
| IMS-O005 | Applicable Australian WHS jurisdiction and other legal obligations | Legal register and reporting triggers depend on work locations/activities | Operating jurisdictions and work profile | Owner/legal or WHS advice |
| IMS-O006 | Essential Eight scope and target maturity | Controls and evidence differ by maturity target | Asset inventory, threats, contracts and client expectations | Owner/security adviser |
| IMS-O007 | Information classification scheme | Drives access, handling, retention and local-memory eligibility | Client data types and contractual controls | Owner |
| IMS-O008 | Whether separate restricted storage is required for certain event types | Item-level access may be insufficient or hard to administer safely | Permission design and sensitivity analysis | Owner/technical review |
| IMS-O009 | Standard copies and edition transition approach | Accurate mappings require authorised text and revision monitoring | Standards access and commercial timing | Owner |
| IMS-O010 | Supplier and contractor scope | Determines procurement, competence and WHS/security controls | Material suppliers and contractor usage | Owner |
| IMS-O011 | Local professional-memory integration scope | Determines what may be indexed locally and how deletion/access changes propagate | Data classification, provenance and security model | Owner/architecture review |
| IMS-O012 | Certification business case and timing | Avoids premature certification overhead | Client demand, tender requirements, cost and operating evidence | Owner |

## 5. Decision gate for tenant implementation

No SharePoint schema, workflow, form, view or navigation change should be approved
until all of the following are recorded:

1. read-only live tenant inventory;
2. Installer v1.6 provenance or an explicit decision to supersede it;
3. field-level reuse/extension matrix;
4. approved IMS scope;
5. approved risk method;
6. approved sensitivity, permission and retention design;
7. test-site deployment and rollback plan;
8. owner approval referencing the reviewed schema version.

The decision log should remain small. New entries are warranted only for choices
that affect scope, sources of truth, authority, access, risk, evidence, deployment
or future compatibility.
