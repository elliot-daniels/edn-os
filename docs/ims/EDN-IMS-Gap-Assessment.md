# EDN IMS Gap Assessment

Status: Baseline assessment from repository evidence only  
Date: 2026-08-05  
Assessment boundary: No live SharePoint inspection and no certification opinion

## 1. Assessment method

This assessment compares the repository-observed EDN Systems OS package with the
capabilities needed for an integrated, certification-ready management system.
It is not a clause-by-clause conformity audit because:

- the live SharePoint tenant was not inspected;
- Installer v1.6 and its list schemas are absent from the repository;
- no controlled policy, procedure, risk, audit or evidence corpus is present;
- the licensed text of the ISO standards was not supplied;
- operating effectiveness cannot be established from deployment code.

Ratings:

- **Present** — directly evidenced in this repository;
- **Partial** — useful foundation exists but lacks IMS requirements;
- **Not evidenced** — may exist elsewhere, but this repository does not prove it;
- **Decision required** — design depends on owner, legal or contractual input.

### 1.1 Complete repository inventory

Git inspection found branch `master` with no commits; every current artifact is
untracked. This is a discovered repository-state fact, not a recommendation to
commit automatically.

| Artifact | Current purpose | IMS observation |
|---|---|---|
| `README.md` | Defines EDN Systems OS and current v2.2 package | Establishes SharePoint as current operational data layer and references missing Installer v1.6 |
| `Documentation/Executive-Dashboard-v2.2.md` | Dashboard information architecture and deployment guidance | Strong authoritative-view principle; no IMS model |
| `Installer/Deploy-ExecutiveDashboard.ps1` | PnP deployment of page, assets, theme and navigation | Reusable idempotent pattern; not a schema/bootstrap installer |
| `SharePoint/dashboard.config.json` | Dashboard navigation and quick-create configuration | Names core operational lists but contains no fields or content types |
| `Releases/v2.2/RELEASE-NOTES.md` | v2.2 release summary | Confirms this is the first repository dashboard release |
| `Branding/Colour Palette/edn-theme.json` | Brand and semantic status colours | Reusable visual language; not control evidence |
| `Branding/Hero Images/edn-executive-hero.png` | Executive hero artwork | Presentation asset only |
| `Branding/Icons/dashboard-icons.svg` | Dashboard icon symbols | Presentation asset only |
| `Branding/Logos/edn-systems-lockup.svg` | EDN Systems wordmark | Presentation asset only |
| `Branding/Logos/edn-systems-mark.svg` | EDN Systems mark | Presentation asset only |

`PowerApps`, `PowerAutomate` and `Templates` exist but contain no files. There are
no repository files named or functioning as a constitution, IMS handoff, tenant
inventory, controlled policy set, provisioning schema, risk register, legal
register, audit programme or standards mapping. The deployment script and
SharePoint configuration were therefore treated as the available provisioning
and SharePoint evidence.

## 2. Current-state strengths

| Strength | Evidence | IMS value |
|---|---|---|
| SharePoint is identified as the operational data layer | `README.md` | Clear current system-of-record boundary |
| Dashboard links to authoritative list views | `Documentation/Executive-Dashboard-v2.2.md` | Avoids duplicate reporting facts |
| Repeatable deployment pattern | `Installer/Deploy-ExecutiveDashboard.ps1` | Foundation for controlled infrastructure changes |
| Human authentication with MFA support | Deployment documentation and script | Supports accountable administration |
| Existing operational concepts | `SharePoint/dashboard.config.json` and deployment script | Projects, Actions, Work Log, Quotes, Approvals, Engineering Knowledge, Executive Metrics and System Status can be reused |
| Status semantic colours | Theme configuration | Consistent operational signalling |
| Forward-compatible dashboard layout | Dashboard documentation | IMS views can be added without replacing the cockpit |

These strengths support integration, but they are not evidence of an operating
quality, WHS or information-security management system.

## 3. Cross-management-system gaps

ISO management system standards share a common operating pattern: organisational
context, leadership, planning, support, operation, performance evaluation and
improvement. The proposed IMS should implement that pattern once.

| Capability | Current rating | Evidence/gap | Required response |
|---|---|---|---|
| IMS scope and boundaries | Not evidenced | No scope statement, exclusions or organisational boundary | Approve one integrated scope covering services, locations, workers, information and technology |
| Context and interested parties | Partial | Clients and Projects are concepts; no stakeholder/requirement model is visible | Extend Clients and create obligations mapping; record worker, regulator, supplier and community needs proportionately |
| Policies and commitments | Not evidenced | No controlled policies | Create one integrated policy set with quality, WHS and information-security commitments |
| Roles, responsibilities and authority | Partial | Lists imply owners/approvers, but schemas are unavailable | Define owner, approver and delegated authority fields; owner remains accountable even when AI assists |
| Risks and opportunities | Not evidenced | No enterprise risk model | Create one integrated register linked to Projects, Clients, Assets and Processes |
| Objectives and plans | Partial | Executive Metrics exists by reference | Extend it with objective, target, owner, period, source and linked Actions |
| Competence and awareness | Partial | Engineering Knowledge exists by reference | Define competency evidence and awareness requirements without creating a training bureaucracy |
| Communication | Not evidenced | No internal/external communication plan | Record only material communications, responsible person and trigger |
| Documented information control | Not evidenced | Repository documentation is not a controlled-document system | Add controlled library metadata, approval, version, review and retirement workflow |
| Operational control | Partial | Projects, Work Log, Actions and Assets are stated/existing concepts | Map operating processes and controls to these records rather than duplicating them |
| Monitoring and measurement | Partial | Dashboard and Executive Metrics provide a presentation foundation | Define metric ownership, calculation provenance, thresholds and review cadence |
| Internal audit/control assessment | Not evidenced | No assurance plan, tests or findings | Add Assurance records with evidence and findings linked to Actions |
| Management review | Not evidenced | Morning brief is operational, not an IMS review | Create concise periodic management-review decision record using existing metrics and risks |
| Nonconformity and corrective action | Partial | Actions can hold work, but source, root cause and effectiveness are absent | Extend Actions and add typed Findings/Events |
| Continual improvement | Partial | Dashboard supports attention management | Create improvement types and effectiveness review, reusing Actions and metrics |
| Provenance and audit history | Partial | SharePoint history and source list links are implied | Add stable record IDs, explicit source/evidence links, approval rationale and retention metadata |

## 4. ISO 9001-aligned quality gaps

Current standard baseline: ISO 9001:2015 remains current as at the assessment
date, with a replacement expected in September 2026. Requirement mappings must
therefore be edition-aware.

| Quality capability | Rating | Gap |
|---|---|---|
| Service and process definition | Partial | Projects and Work Log exist conceptually; end-to-end processes, inputs, outputs and owners are not documented |
| Customer and contract requirements | Partial | Clients and Quotes exist conceptually; review, assumptions, changes and acceptance evidence are not defined |
| Design/development control | Not evidenced | Engineering design inputs, reviews, verification, validation and change control are not modelled |
| Supplier/external-provider control | Not evidenced | No supplier approval, performance or purchased-service control model |
| Service delivery and release | Partial | Work Log and Projects can evidence delivery; acceptance and release criteria are not defined |
| Nonconforming output | Not evidenced | No disposition, concession or client-notification record |
| Customer feedback and complaints | Not evidenced | No feedback/complaint type or trend metric |
| Quality objectives and performance | Partial | Executive Metrics is a reusable structure; quality measures are undefined |
| Corrective action effectiveness | Not evidenced | Actions lack evidenced root cause and effectiveness review |

Priority quality outcome: define the small set of processes that consistently
turn a client requirement into an accepted engineering deliverable, then control
exceptions and improvement through existing operational records.

## 5. ISO 45001-aligned WHS gaps

ISO 45001:2018 is current and emphasises leadership, worker participation,
hazard identification, legal compliance, operational control, emergency response,
incident investigation and improvement.

| WHS capability | Rating | Gap |
|---|---|---|
| Worker consultation and participation | Not evidenced | No consultation record or mechanism; one-person status does not remove contractor/worker consultation duties |
| Hazard identification | Not evidenced | No hazard/event model linked to sites, projects, assets or tasks |
| WHS legal and other requirements | Not evidenced | No jurisdiction-aware obligation register |
| WHS risk assessment and controls | Not evidenced | No approved WHS consequence scale, hierarchy-of-controls field or residual assessment |
| Change management | Not evidenced | Project/asset changes do not visibly trigger WHS review |
| Procurement and contractors | Not evidenced | No contractor competence, induction, supervision or supplier safety controls |
| Emergency preparedness | Not evidenced | No emergency scenarios, contacts, tests or lessons |
| Incident/near-miss reporting | Not evidenced | No restricted WHS event workflow or reportability decision |
| Health monitoring and sensitive records | Decision required | Privacy and access model must be defined before any such records are stored |
| WHS performance and review | Not evidenced | No leading/lagging indicators or periodic review evidence |

Priority WHS outcome: establish a proportionate hazard/incident workflow, legal
obligation ownership and project/task risk linkage before building dashboards.

## 6. ISO/IEC 27001-aligned information-security gaps

ISO/IEC 27001:2022 requires a risk-based information security management system
covering people, policy and technology. Tool deployment alone is not conformity.

| Security capability | Rating | Gap |
|---|---|---|
| ISMS scope and information context | Not evidenced | No system, service, information or supplier boundary |
| Information-security risk method | Not evidenced | No CIA impact criteria, risk acceptance criteria or treatment plan |
| Asset and information inventory | Partial | Assets is owner-stated but schema/coverage are not evidenced |
| Information classification and handling | Not evidenced | No classification, owner, handling or retention fields |
| Control catalogue and applicability | Not evidenced | No control ownership, applicability rationale or Statement of Applicability view |
| Access and privilege governance | Partial | Deployment requires authenticated PnP access; operational access reviews are absent |
| Supplier/cloud security | Not evidenced | Microsoft 365, applications and suppliers are not assessed as dependencies |
| Security logging and monitoring | Partial | System Status exists conceptually; event sources, retention and review are undefined |
| Incident response | Not evidenced | No security event classification, response plan, communications or lessons workflow |
| Backup, continuity and recovery | Not evidenced | No criticality, backup control, restoration test or recovery objective evidence |
| Compliance and assurance | Not evidenced | No control tests, internal audit or exception approvals |

Priority security outcome: inventory information/assets and approve a security
risk method before selecting control maturity or declaring implementation.

## 7. Essential Eight gap

The repository contains no technical configuration or assessment evidence for any
Essential Eight strategy. All current maturity ratings are therefore **unknown**,
not Level Zero and not Level One.

| Strategy | Current evidence | Required planning record |
|---|---|---|
| Application control | None | Scope, platform capability, exceptions, test evidence |
| Patch applications | None | Asset discovery, vulnerability/patch cadence, critical-response evidence |
| Configure Microsoft Office macros | None | Policy scope, trusted locations/signing, exception approval |
| User application hardening | None | Browser/PDF/Office configuration baseline and verification |
| Restrict administrative privileges | None | Privileged inventory, justification, separate accounts, review and expiry |
| Patch operating systems | None | OS/network device inventory, scanning and patch evidence |
| Multi-factor authentication | Partial only for deployment login | Identity scope, MFA strength, exclusions and test evidence |
| Regular backups | None | Critical data scope, isolation, retention, monitoring and restoration tests |

ASD advises choosing a risk-appropriate target, implementing the strategies as a
set, documenting exceptions and compensating controls, and reaching the same
maturity level across all eight before moving higher. Maturity Level One may be a
reasonable small-business planning hypothesis, but EDN must not adopt or claim it
until asset, threat, client and contractual discovery is complete.

## 8. ISO 31000-informed risk gap

No risk framework, criteria, appetite, register or review evidence is present.
The proposed single risk model must include:

- scope, context and criteria;
- stakeholder communication and consultation;
- identification, analysis and evaluation;
- treatment selection and Action ownership;
- monitoring and review;
- recording and reporting;
- explicit human risk acceptance.

ISO 31000 is guidance, not a certifiable management system. It should inform the
shared process instead of becoming another compliance module.

## 9. Future extension readiness

| Future framework | Reusable core | Missing domain-specific capability |
|---|---|---|
| ISO 14001 | Obligations, risks, controls, objectives, assurance, documents | Environmental aspects/impacts, lifecycle perspective, compliance obligations and performance indicators |
| ISO 22301 | Assets, risks, controls, events, tests, management review | Business impact analysis, recovery objectives, continuity strategies and exercise programme |
| DISP | Security obligations, assets, people, suppliers, incidents, approvals | Membership scope, governance, personnel/physical/cyber controls and Defence-specific evidence requirements |

No future framework requires a new foundational register if the shared model is
implemented correctly.

## 10. Component disposition

### Reuse

- SharePoint as the current operational system of record and UI.
- Executive Dashboard as the integrated cockpit.
- Projects, Clients, Actions, Assets, Approvals, Executive Metrics and System
  Status as authoritative operational structures, subject to schema discovery.
- Work Log, Quotes and Engineering Knowledge for execution evidence.
- Native SharePoint list views, versioning and permission controls.
- Idempotent PnP deployment approach after discovery and approval.

### Extend

- Actions with treatment/corrective/improvement provenance and effectiveness.
- Approvals with typed human decisions, rationale, expiry and source.
- Assets with ownership, criticality, classification and control scope.
- Executive Metrics with objectives and calculation provenance.
- System Status with control checks and event/finding links.
- Dashboard navigation and sections only after the information model operates.

### Rename or clarify

- Use **Assurance, Events and Findings** rather than separate audit,
  nonconformity, complaint, hazard and incident registers.
- Use **Risks and Opportunities** rather than an ISO risk register.
- Use **Obligations and Requirements** rather than a standards register.
- Use **Processes and Controls** rather than separate QMS/WHS/ISMS control lists.

### Retire or avoid

- Separate ISO 9001, ISO 45001, ISO/IEC 27001 and Essential Eight portals.
- Duplicate Actions, project risks, asset inventories or evidence libraries.
- Static dashboard numbers and compliance scores without source records.
- AI-generated approvals, risk acceptance, closure or conformity claims.
- Sprint-named permanent schemas and standard-named software modules.

## 11. Overengineering risks for a one-person business

| Risk | Consequence | Guardrail |
|---|---|---|
| Too many registers | Administration displaces billable and risk-reducing work | Five shared IMS structures maximum before a demonstrated access/legal need |
| Excessive mandatory metadata | Records are not created or become inaccurate | Minimum viable fields plus conditional fields by type/risk |
| Workflow theatre | Owner approves their own low-risk records repeatedly without value | Reserve formal Approval for policies, risk acceptance, exceptions and closure requiring attestation |
| Clause-first design | Operations bend around standards rather than business outcomes | Design processes first; map requirements second |
| Dashboard-first implementation | Attractive views mask absent controls and evidence | Provision data model and operating routines before IMS dashboard tiles |
| Premature Power Apps | Maintenance burden and lock-in | Use native forms/views first; customise only proven pain points |
| Automation without exception handling | Silent failures damage auditability | Monitor flows in System Status and preserve human recovery paths |
| False maturity claims | Commercial and assurance risk | Distinguish planned, implemented, operating and effective; require evidence |
| Sensitive-data commingling | Inappropriate access to WHS/security/client records | Design permissions and retention before storing sensitive events |
| Standards churn | Rework when editions change | Version frameworks and mappings independently of business records |

## 12. Highest-priority gaps

1. The live list/library schemas and Installer v1.6 source are not available for
   analysis; duplicate-safe design cannot be finalised without discovery.
2. There is no approved IMS scope, context, policy or authority model.
3. There is no integrated risk method or risk-and-opportunity register.
4. There is no controlled-document or requirement/control mapping model.
5. There is no event/finding, assurance or corrective-action effectiveness model.
6. There is no evidence-based Essential Eight baseline.
7. Sensitive-record access and retention requirements are unresolved.

The next phase should close the discovery gap before any provisioning occurs.
