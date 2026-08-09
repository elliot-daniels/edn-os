# EDN IMS Target SharePoint Schema

Status: Implementation-ready design; deployment not authorised  
Date: 2026-08-09  
Evidence: Corrected IMS-003 rerun only

## 1. Design rules

- Preserve all existing list/library GUIDs, URLs and internal field names.
- Add fields; do not rename or delete existing internal fields.
- Proposed internal names use stable `IMS` prefixes and remain unchanged if
  display terminology changes.
- New fields are optional during migration unless explicitly stated. Required
  rules should initially be enforced through views/process validation, not by
  making populated lists impossible to edit.
- `AI` values are `No`, `Draft` (AI may propose with source and human review), or
  `Calc` (deterministic calculation only). `Approval` means a human Approval
  record is mandatory for the authoritative state.
- `Backfill`: N none, O optional enrichment, D deterministic, A AI-assisted draft
  with provenance, H human review, M mandatory human decision.
- `Rollback`: hide removes from forms/views but retains data; disable stops a
  calculation/workflow; no proposed field is deleted on rollback.
- All Person fields use SharePoint Person; URL fields use Hyperlink; stable IDs
  use indexed single-line Text with unique-value enforcement where supported.
- Permissions, content types, Power Platform definitions and Purview settings
  remain **unknown** pending separately approved discovery.

Table columns compact the complete field contract: required/default/choices;
indexing; lookup target and multiplicity; purpose/domain; provenance, AI and
approval boundary; backfill and rollback.

## 2. Existing authoritative structures — minimum extensions

### Projects

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| IMS relevance / `IMSRelevance` | Choice | O; Not assessed; Not assessed, In scope, Out of scope | Yes | — / No | Scope filter / all | Source rationale required when out; Draft; No | A+H; hide |
| Related risks / `IMSRelatedRisks` | Lookup | O; blank | No | Risks and Opportunities / Yes | Project risk context / all | Target IDs; Draft; No | O; hide |
| Related controls / `IMSRelatedControls` | Lookup | O; blank | No | Processes and Controls / Yes | Applied controls / all | Target IDs; Draft; No | O; hide |
| Related obligations / `IMSRelatedObligations` | Lookup | O; blank | No | Obligations and Requirements / Yes | Contract/legal context / quality, commercial | Target IDs; Draft; No | O; hide |
| Related findings / `IMSRelatedFindings` | Lookup | O; blank | No | Assurance, Events and Findings / Yes | Assurance context / all | Target IDs; Draft; No | O; hide |

### Clients

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Requirement summary / `IMSClientRequirementSummary` | Multiple lines plain | O; blank | No | — | Concise interpreted needs / quality, commercial | Source URL required; Draft; human confirms | A+H; hide |
| Assurance needs / `IMSAssuranceNeeds` | Multiple lines plain | O; blank | No | — | Client evidence/reporting expectations / assurance | Contract/source required; Draft; human confirms | A+H; hide |
| Information classification / `IMSInformationClassification` | Choice | O; EDN Internal; configured classifications | Yes | — | Handling baseline / security | Contract/policy source; Draft; human confirms | H; hide |
| Requirements review date / `IMSRequirementsReviewDate` | Date only | O; blank | Yes | — | Periodic client requirement review / quality | Review evidence; No; No | H; hide |

### Actions

Existing `ActionType`, owner and due-date fields should be reused if their live
semantics are confirmed; do not create synonyms.

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| IMS action ID / `IMSActionID` | Text | New records; generated | Yes/unique | — | Durable action identity / all | Creation provenance; Calc; No | D; hide |
| Source type / `IMSSourceType` | Choice | O; blank; Risk, Opportunity, Event/Finding, Audit, Project, Client, Control, Other | Yes | — | Polymorphic source discriminator / all | Required with source ID; Draft; human confirms | A+H; hide |
| Source record ID / `IMSSourceRecordID` | Text | O; blank | Yes | — | Durable originating record / all | Must resolve; Draft; No | O; hide |
| Source reference / `IMSSourceReference` | Hyperlink | O; blank | No | — | Navigable provenance / all | Must be valid source; Draft; No | O; hide |
| Effectiveness status / `IMSEffectivenessStatus` | Choice | O; Not required; Not required, Pending, Effective, Ineffective | Yes | — | Verify outcome / improvement | Evidence when assessed; Draft; human confirms | H; hide |
| Closure approval / `IMSClosureApproval` | Lookup | O; blank | No | Approvals / No | Governed closure where required / all | Approval ID; No; Yes by action type | H; hide |

### Assets

No separate Asset Register is designed. Metadata applies only when meaningful to
documents in the existing `Assets` library.

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Asset class / `IMSAssetClass` | Choice | O; Other; Information, Software, Service, Physical, Other | Yes | — | Documented asset context / security, operations | Source/document context; Draft; human confirms | A+H; hide |
| Asset owner / `IMSAssetOwner` | Person | O; blank | Yes | — | Accountability / security | Human assignment; No; human confirms | H; hide |
| Criticality / `IMSCriticality` | Choice | O; Not assessed; Not assessed, Low, Medium, High, Critical | Yes | — | Prioritise controls/recovery / security, continuity | Assessment source; Draft; human confirms | H; hide |
| Information classification / `IMSInformationClassification` | Choice | O; EDN Internal; configured values | Yes | — | Handling / security | Policy/source; Draft; human confirms | H; hide |
| Related controls / `IMSRelatedControls` | Lookup | O; blank | No | Processes and Controls / Yes | Applicable controls / security | Target IDs; Draft; No | O; hide |

### Approvals

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| IMS approval ID / `IMSApprovalID` | Text | New records; generated | Yes/unique | — | Durable decision identity / governance | Creation provenance; Calc; No | D; hide |
| Decision type / `IMSDecisionType` | Choice | New records; Other; Document approval, Risk acceptance, Exception, Closure, Management review, Other | Yes | — | Decision routing / all | Source required; Draft; human confirms | H; hide |
| Decision / `IMSDecision` | Choice | New records; Pending; Pending, Approved, Rejected, Accepted, Conditional, Withdrawn | Yes | — | Authoritative human outcome / governance | Named approver/timestamp; No; **Yes** | M; hide, never recalculate |
| Rationale / `IMSRationale` | Multiple lines plain | Required when decided; blank | No | — | Explain decision / governance | Human authored; Draft text permitted; **Yes** | H; hide |
| Subject type / `IMSSubjectType` | Choice | New records; Other; Document, Risk, Finding, Action, Quote, Exception, Other | Yes | — | Polymorphic target / all | Paired subject ID; Draft; human confirms | H; hide |
| Subject record ID / `IMSSubjectRecordID` | Text | New records; blank | Yes | — | Durable decision target / all | Must resolve; Draft; human confirms | H; hide |
| Subject reference / `IMSSubjectReference` | Hyperlink | O; blank | No | — | Navigable target / all | Valid URL; Draft; No | O; hide |
| Review/expiry date / `IMSDecisionReviewDate` | Date only | O; blank | Yes | — | Time-bound decisions / governance | Decision context; Draft; human confirms | H; hide |

### Executive Metrics

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| IMS domain / `IMSDomain` | Choice | O; Other; configured domains | Yes | — | Filter metrics / all | Metric definition; Draft; human confirms | H; hide |
| Objective / `IMSObjective` | Multiple lines plain | O; blank | No | — | Intended result / performance | Owner source; Draft; human confirms | H; hide |
| Target / `IMSTarget` | Text | O; blank | No | — | Target preserving unit/expression / performance | Owner source; Draft; human confirms | H; hide |
| Calculation source / `IMSCalculationSource` | Hyperlink | O; blank | No | — | Metric provenance / assurance | Valid source; No; No | O; hide |
| Threshold status / `IMSThresholdStatus` | Choice | O; Unknown; Unknown, On target, Watch, Off target | Yes | — | Consistent signal / performance | Calculation evidence; Calc; human reviews | D where formula exists; disable/hide |
| Related control / `IMSRelatedControl` | Lookup | O; blank | Yes | Processes and Controls / No | What is measured / assurance | Target ID; Draft; No | O; hide |

### System Status

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Control owner / `IMSControlOwner` | Person | O; blank | Yes | — | Monitoring accountability / security, assurance | Human assignment; No; human confirms | H; hide |
| Last check / `IMSLastCheckDate` | Date/time | O; blank | Yes | — | Monitoring recency / assurance | System/manual evidence; Calc; No | D; disable/hide |
| Evidence reference / `IMSEvidenceReference` | Hyperlink | O; blank | No | — | Check evidence / assurance | Valid source; No; No | O; hide |
| Related control / `IMSRelatedControl` | Lookup | O; blank | Yes | Processes and Controls / No | Monitoring target / assurance | Target ID; Draft; No | O; hide |
| Related finding / `IMSRelatedFinding` | Lookup | O; blank | No | Assurance, Events and Findings / No | Exception escalation / assurance | Target ID; Draft; No | O; hide |

### Work Log

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Related control / `IMSRelatedControl` | Lookup | O; blank | Yes | Processes and Controls / No | Operating evidence / assurance | Target ID; Draft; No | O; hide |
| Related action / `IMSRelatedAction` | Lookup | O; blank | Yes | Actions / No | Work performed on action / improvement | Target ID; Draft; No | O; hide |
| Related finding / `IMSRelatedFinding` | Lookup | O; blank | Yes | Assurance, Events and Findings / No | Investigation/correction evidence / assurance | Target ID; Draft; No | O; hide |

### Quotes

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Requirement summary / `IMSRequirementSummary` | Multiple lines plain | O; blank | No | — | Reviewed client needs / quality, commercial | Source quote/client material; Draft; human confirms | A+H; hide |
| Assumptions / `IMSAssumptions` | Multiple lines plain | O; blank | No | — | Delivery/commercial basis / commercial | Human-authored/source; Draft; human confirms | A+H; hide |
| Exclusions / `IMSExclusions` | Multiple lines plain | O; blank | No | — | Scope boundary / quality, commercial | Human-authored/source; Draft; human confirms | A+H; hide |
| Related risks / `IMSRelatedRisks` | Lookup | O; blank | No | Risks and Opportunities / Yes | Bid/delivery risk / commercial | Target IDs; Draft; No | O; hide |
| Approval / `IMSApproval` | Lookup | O; blank | Yes | Approvals / No | Quote approval / governance | Approval ID; No; Yes when policy requires | H; hide |

### Engineering Knowledge

| Display / internal | Type | Required, default, choices | Index | Lookup / multi | Purpose / domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Knowledge type / `IMSKnowledgeType` | Choice | O; Reference; Method, Standard interpretation, Lesson, Reference, Template guidance | Yes | — | Lifecycle/view / quality, engineering | Source record; Draft; human confirms | A+H; hide |
| Technical owner / `IMSTechnicalOwner` | Person | O; blank | Yes | — | Accountability / engineering | Human assignment; No; human confirms | H; hide |
| Review status / `IMSReviewStatus` | Choice | O; Draft; Draft, Reviewed, Approved, Superseded, Retired | Yes | — | Authority state / knowledge | Approval/evidence; Draft classification only; human confirms | H; hide |
| Related controls / `IMSRelatedControls` | Lookup | O; blank | No | Processes and Controls / Yes | Control support / assurance | Target IDs; Draft; No | O; hide |
| Source reference / `IMSSourceReference` | Hyperlink | O; blank | No | — | Provenance / knowledge | Valid source; Draft; No | O; hide |

## 3. Risks and Opportunities

Extend the existing empty `Risk Register`; preserve its URL/GUID. Use “Risks and
Opportunities” as navigation/display terminology only until dependency review.

| Display / internal | Type | Req/default/choices | Index | Lookup/multi | Purpose/domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Record ID / `IMSRiskID` | Text | R new/generated | Yes/unique | — | Durable identity/all | Creation; Calc; No | D; hide |
| Record type / `IMSRiskType` | Choice | R; Risk; Risk, Opportunity | Yes | — | Shared model/all | Human source; Draft; human confirms | M; hide |
| Domain / `IMSDomain` | Choice | R new; configured domains | Yes | — | Context/all | Assessment; Draft; human confirms | H; hide |
| Description / `IMSDescription` | Multiple lines plain | R new | No | — | Risk/opportunity statement/all | Source required; Draft; human confirms | H; hide |
| Likelihood / `IMSLikelihood` | Number integer 1–5 | Conditional for Risk | Yes | — | Inherent probability/all | Assessment rationale; Draft; human confirms | M; hide |
| Consequence / `IMSConsequence` | Number integer 1–5 | Conditional for Risk | Yes | — | Inherent impact/all | Assessment rationale; Draft; human confirms | M; hide |
| Inherent score / `IMSInherentScore` | Number integer | Calculated, blank until inputs | Yes | — | L×C/all | Input fields; Calc; No | D; disable calculation/hide |
| Inherent rating / `IMSInherentRating` | Choice | Calculated; Low/Moderate/High/Extreme | Yes | — | Treatment priority/all | Score thresholds; Calc; No | D; disable/hide |
| Owner / `IMSRiskOwner` | Person | R new | Yes | — | Accountability/all | Human assignment; No; human confirms | M; hide |
| Treatment decision / `IMSTreatmentDecision` | Choice | O; Assess; Assess, Treat, Tolerate, Transfer, Avoid, Pursue, Decline | Yes | — | Response/all | Rationale/source; Draft; human confirms | H; hide |
| Related actions / `IMSRelatedActions` | Lookup | O | No | Actions/Yes | Treatment/all | Target IDs; Draft; No | O; hide |
| Review date / `IMSReviewDate` | Date only | R new | Yes | — | Review cadence/all | Owner decision; Draft; human confirms | M; hide |
| Residual likelihood / `IMSResidualLikelihood` | Number integer 1–5 | Conditional after controls | Yes | — | Post-treatment probability/all | Evidence/rationale; Draft; human confirms | H; hide |
| Residual consequence / `IMSResidualConsequence` | Number integer 1–5 | Conditional after controls | Yes | — | Post-treatment impact/all | Evidence/rationale; Draft; human confirms | H; hide |
| Residual score / `IMSResidualScore` | Number integer | Calculated | Yes | — | Residual L×C/all | Inputs; Calc; No | D; disable/hide |
| Residual rating / `IMSResidualRating` | Choice | Calculated | Yes | — | Acceptance/escalation/all | Thresholds; Calc; No | D; disable/hide |
| Status / `IMSRiskStatus` | Choice | R new; Draft; Draft, Active, Treatment, Monitoring, Accepted, Closed, Realised | Yes | — | Lifecycle/all | Status evidence; Draft except Accepted; human confirms | M; hide |
| Acceptance approval / `IMSAcceptanceApproval` | Lookup | Required for Accepted | Yes | Approvals/No | Human acceptance/governance | Approval record; No; **Yes** | M; hide, never auto-set |
| Acceptance authority / `IMSAcceptanceAuthority` | Person | Required for Accepted | Yes | — | Named accountable person/governance | From approval; No; **Yes** | M; hide |
| Acceptance date / `IMSAcceptanceDate` | Date/time | Required for Accepted | Yes | — | Decision timestamp/governance | From approval; No; **Yes** | M; hide |
| Source reference / `IMSSourceReference` | Hyperlink | O | No | — | Provenance/all | Valid source; Draft; No | O; hide |
| Evidence reference / `IMSEvidenceReference` | Hyperlink | O | No | — | Assessment evidence/all | Valid source; Draft; No | O; hide |
| Related project/client/control | `IMSRelatedProject`, `IMSRelatedClient`, `IMSRelatedControls` Lookup | O | Yes for singles | Projects/No; Clients/No; Controls/Yes | Context/all | Target IDs; Draft; No | O; hide |

## 4. Controlled Documents (`SOPs & Templates`)

Retain the existing library URL and technical identity. Recommended navigation
label: **Controlled Documents**. A physical rename offers little value and may
break bookmarks, scripts or user expectations; defer it until dependencies are
known. SharePoint's native version is authoritative; `IMSDocumentVersion` is a
human-facing approved revision label, not a replacement for version history.

| Display / internal | Type | Req/default/choices | Index | Lookup/multi | Purpose/domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Document ID / `IMSDocumentID` | Text | R new/generated | Yes/unique | — | Durable identity/all | Creation; Calc; No | D; hide |
| Document type / `IMSDocumentType` | Choice | R new; Procedure; Policy, Procedure, Plan, Form, Template, Work instruction | Yes | — | Lifecycle/all | Human classification; Draft; human confirms | H; hide |
| Document owner / `IMSDocumentOwner` | Person | R new | Yes | — | Accountability/all | Human assignment; No; human confirms | M; hide |
| Approved revision / `IMSDocumentVersion` | Text | O | Yes | — | Business revision/all | Approved document; Draft; human confirms | H; hide |
| Approval status / `IMSApprovalStatus` | Choice | R new; Draft; Draft, In review, Approved, Superseded, Retired | Yes | — | Lifecycle/governance | Approval link; No for Approved; **Yes** | M; hide |
| Approval / `IMSApproval` | Lookup | Required for Approved | Yes | Approvals/No | Human decision/governance | Approval ID; No; **Yes** | M; hide |
| Approver / `IMSApprover` | Person | Derived from Approval | Yes | — | Visible authority/governance | Approval ID; Calc-copy; **Yes** | D; hide |
| Approval date / `IMSApprovalDate` | Date/time | Derived for Approved | Yes | — | Decision date/governance | Approval ID; Calc-copy; **Yes** | D; hide |
| Effective date / `IMSEffectiveDate` | Date only | Required for Approved | Yes | — | Effective control/all | Approval; No; **Yes** | M; hide |
| Review date / `IMSReviewDate` | Date only | Required for Approved | Yes | — | Periodic review/all | Owner/approval; Draft; human confirms | M; hide |
| Supersedes / `IMSSupersedes` | Lookup | O | No | Same library/No | Revision chain/all | Target document ID; Draft; human confirms | O; hide |
| Classification / `IMSInformationClassification` | Choice | R new; EDN Internal; configured | Yes | — | Handling/security | Policy/source; Draft; human confirms | H; hide |
| Applicable controls / `IMSRelatedControls` | Lookup | O | No | Processes and Controls/Yes | Governed controls/all | Target IDs; Draft; No | O; hide |
| Source reference / `IMSSourceReference` | Hyperlink | O | No | — | Origin/provenance | Valid source; Draft; No | O; hide |

## 5. Obligations and Requirements

Create one GenericList only after IMS-006E approval. Store EDN-authored summaries
and source references; never reproduce licensed ISO text.

| Display / internal | Type | Req/default/choices | Index | Lookup/multi | Purpose/domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Requirement ID / `IMSRequirementID` | Text | R/generated | Yes/unique | — | Durable identity/all | Creation; Calc; No | N; hide list |
| Requirement type / `IMSRequirementType` | Choice | R; Internal; Legislation, Regulation, Standard, Contract, Client, Internal | Yes | — | Source class/all | Source; Draft; human confirms | N; hide |
| Framework/source / `IMSFramework` | Text | R | Yes | — | Issuer/framework/all | Authoritative source; Draft; human confirms | N; hide |
| Edition/version / `IMSEdition` | Text | O | Yes | — | Change awareness/all | Source; Draft; human confirms | N; hide |
| Reference / `IMSRequirementReference` | Text | R | Yes | — | Clause/control/reference/all | Source; Draft; human confirms | N; hide |
| EDN interpretation / `IMSInterpretation` | Multiple lines plain | R | No | — | Actionable summary/all | Source URL; Draft; human confirms | N; hide |
| Applicability / `IMSApplicability` | Choice | R; Under review; Under review, Applicable, Not applicable | Yes | — | Scope/governance | Rationale; Draft; human confirms | N; hide |
| Applicability rationale / `IMSApplicabilityRationale` | Multiple lines plain | Required when decided | No | — | Decision basis/governance | Human/source; Draft; human confirms | N; hide |
| Owner / `IMSRequirementOwner` | Person | R | Yes | — | Accountability/all | Human assignment; No; human confirms | N; hide |
| Review date / `IMSReviewDate` | Date only | R | Yes | — | Version review/all | Owner/source; Draft; human confirms | N; hide |
| Source reference / `IMSSourceReference` | Hyperlink | R | No | — | Authoritative provenance/all | Valid source; Draft; human confirms | N; hide |
| Related controls / `IMSRelatedControls` | Lookup | O | No | Processes and Controls/Yes | Implementation mapping/all | Target IDs; Draft; human confirms | N; hide |
| Related project / client | `IMSRelatedProject`, `IMSRelatedClient` Lookup | O | Yes | Projects/No; Clients/No | Context/quality, commercial | Target IDs; Draft; No | N; hide |
| Status / `IMSRequirementStatus` | Choice | R; Draft; Draft, Current, Superseded, Retired | Yes | — | Lifecycle/all | Review evidence; Draft; human confirms | N; hide |

## 6. Processes and Controls

Create one GenericList. `IMSRecordType` distinguishes Process and Control.

| Display / internal | Type | Req/default/choices | Index | Lookup/multi | Purpose/domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Record ID / `IMSControlID` | Text | R/generated | Yes/unique | — | Durable identity/all | Creation; Calc; No | N; hide list |
| Record type / `IMSRecordType` | Choice | R; Control; Process, Control | Yes | — | Shared catalogue/all | Human; Draft; human confirms | N; hide |
| Domain / `IMSDomain` | Choice | R; configured | Yes | — | Context/all | Human; Draft; human confirms | N; hide |
| Purpose / `IMSPurpose` | Multiple lines plain | R | No | — | Intended outcome/all | Owner/source; Draft; human confirms | N; hide |
| Owner / `IMSControlOwner` | Person | R | Yes | — | Accountability/all | Human assignment; No; human confirms | N; hide |
| Status / `IMSControlStatus` | Choice | R; Draft; Draft, Planned, Operating, Suspended, Retired | Yes | — | Lifecycle/all | Evidence; Draft; human confirms | N; hide |
| Frequency / `IMSOperatingFrequency` | Choice | O; As needed; Continuous, Daily, Weekly, Monthly, Quarterly, Annual, As needed | Yes | — | Operating cadence/assurance | Owner; Draft; human confirms | N; hide |
| Review date / `IMSReviewDate` | Date only | R | Yes | — | Governance/all | Owner; Draft; human confirms | N; hide |
| Related obligations / `IMSRelatedObligations` | Lookup | O | No | Obligations/Yes | Requirement mapping/all | Target IDs; Draft; human confirms | N; hide |
| Related risks / `IMSRelatedRisks` | Lookup | O | No | Risks/Yes | Treatment mapping/all | Target IDs; Draft; human confirms | N; hide |
| Evidence expectation / `IMSEvidenceExpectation` | Multiple lines plain | O | No | — | What demonstrates operation/assurance | Owner/source; Draft; human confirms | N; hide |
| Controlled documents / `IMSControlledDocuments` | Lookup | O | No | SOPs & Templates/Yes | Procedure/policy links/all | Target IDs; Draft; No | N; hide |
| Effectiveness status / `IMSEffectivenessStatus` | Choice | O; Not assessed; Not assessed, Effective, Partly effective, Ineffective | Yes | — | Assurance/all | Assessment evidence; Draft; human confirms | N; hide |
| Evidence reference / `IMSEvidenceReference` | Hyperlink | O | No | — | Latest representative evidence/assurance | Valid source; Draft; No | N; hide |

## 7. Assurance, Events and Findings

Create a standard-access GenericList for non-sensitive metadata. If the approved
permission design shows that restricted categories cannot be safely maintained
there, deploy a restricted companion list using the same field contract and a
non-sensitive cross-reference. Prefer library/list-level boundaries over unique
permissions per item.

Approved initial types: Audit, Inspection, Incident, Nonconformance, Observation,
Finding, Improvement, Security Event, WHS Event, Client Issue. Types may be
disabled in configuration until an operating use exists.

| Display / internal | Type | Req/default/choices | Index | Lookup/multi | Purpose/domain | Provenance; AI; approval | Backfill; rollback |
|---|---|---|---|---|---|---|---|
| Record ID / `IMSEventID` | Text | R/generated | Yes/unique | — | Durable identity/all | Creation; Calc; No | N; hide list |
| Record type / `IMSEventType` | Choice | R; configured initial types | Yes | — | Typed workflow/all | Source; Draft; human confirms | N; hide |
| Domain / `IMSDomain` | Choice | R; configured | Yes | — | Governance view/all | Source; Draft; human confirms | N; hide |
| Event date / `IMSEventDate` | Date/time | R | Yes | — | Occurrence/assessment date/all | Source; Draft; human confirms | N; hide |
| Severity / `IMSSeverity` | Choice | R; Not assessed; Not assessed, Low, Moderate, High, Critical | Yes | — | Triage/all | Assessment/source; Draft; human confirms | N; hide |
| Status / `IMSEventStatus` | Choice | R; Open; Open, Triaged, Investigating, Actioning, Effectiveness review, Closed | Yes | — | Lifecycle/all | Evidence; Draft; human confirms | N; hide |
| Owner / `IMSEventOwner` | Person | R | Yes | — | Accountability/all | Human assignment; No; human confirms | N; hide |
| Summary / `IMSSummary` | Multiple lines plain | R | No | — | Minimal factual description/all | Source required; Draft; human confirms | N; hide |
| Sensitive category / `IMSSensitiveCategory` | Choice | R; None; None, WHS, Information security, Personnel, Client confidential, Investigation | Yes | — | Route to safe boundary/security | Human/source; Draft; human confirms | N; hide |
| Source reference / `IMSSourceReference` | Hyperlink | O | No | — | Provenance/all | Valid source; Draft; No | N; hide |
| Evidence reference / `IMSEvidenceReference` | Hyperlink | O | No | — | Supporting evidence/assurance | Authorised source; Draft; No | N; hide |
| Related project / client | `IMSRelatedProject`, `IMSRelatedClient` Lookup | O | Yes | Projects/No; Clients/No | Context/all | Target IDs; Draft; No | N; hide |
| Related obligation / control / risk | `IMSRelatedObligation`, `IMSRelatedControl`, `IMSRelatedRisk` Lookup | O | Yes | Corresponding catalogues/No | Governance mapping/all | Target IDs; Draft; human confirms mappings | N; hide |
| Related actions / `IMSRelatedActions` | Lookup | O | No | Actions/Yes | Response/improvement/all | Target IDs; Draft; No | N; hide |
| Investigation status / `IMSInvestigationStatus` | Choice | O; Not required; Not required, Pending, In progress, Complete | Yes | — | Investigation control/assurance | Evidence; Draft; human confirms | N; hide |
| Reportability status / `IMSReportabilityStatus` | Choice | O; Not assessed; Not assessed, Not reportable, Advice required, Reportable, Reported | Yes | — | Legal/client decision/WHS, security | Human/specialist evidence; **No**; human only | N; hide |
| Closure approval / `IMSClosureApproval` | Lookup | Conditional by type/severity | Yes | Approvals/No | Authoritative closure/governance | Approval ID; No; **Yes** | N; hide |
| Effectiveness status / `IMSEffectivenessStatus` | Choice | O; Not required; Not required, Pending, Effective, Ineffective | Yes | — | Verify correction/improvement | Evidence; Draft; human confirms | N; hide |
| Review date / `IMSReviewDate` | Date only | O | Yes | — | Follow-up/all | Owner; Draft; human confirms | N; hide |

Sensitive narrative, health details, credentials, exploit detail, legal advice and
investigation evidence must not be stored in broadly accessible metadata fields.
The standard list may hold a minimal restricted-record stub and link only if that
does not disclose sensitive facts.

## 8. Risk calculation and workflow

Use integer scales from 1 to 5.

| Score | Likelihood | Consequence |
|---:|---|---|
| 1 | Rare | Insignificant |
| 2 | Unlikely | Minor |
| 3 | Possible | Moderate |
| 4 | Likely | Major |
| 5 | Almost certain | Severe |

`score = likelihood × consequence`. Ratings: Low 1–4, Moderate 5–9, High
10–16, Extreme 17–25. Inherent and residual scores use the same deterministic
calculation. Opportunity records may use the same likelihood scale and a positive
benefit interpretation of consequence; treatment choices are Pursue, Enhance,
Share or Decline, configured without pretending opportunity acceptance is risk
acceptance.

Workflow: Draft → assess inherent → choose response/actions → implement controls
→ assess residual → monitor or seek acceptance → review → close/supersede.

- Low: owner may monitor; acceptance still recorded if status is Accepted.
- Moderate: treatment or documented acceptance and scheduled review.
- High: treatment plan and explicit owner approval before acceptance.
- Extreme: immediate escalation; cannot be accepted until the owner has reviewed
  the basis and any specialist/legal/client escalation required by context.
- Overdue reviews are flagged in views and reminders; automation must not alter
  ratings, close the record or accept it.
- Acceptance status can be set only when the Approval lookup, authority and date
  resolve to a human decision. Calculation automation is allowed; acceptance
  automation is prohibited.

Exact acceptance authorities beyond the owner and any jurisdiction/client-driven
specialist escalation remain a configuration decision before deployment.

## 9. Collision and deployment validation

Before provisioning, compare every proposed internal name case-insensitively
against the target object. If a semantically equivalent existing field exists,
map and reuse it instead of creating another. Reject a collision with a different
type or meaning. Validate all lookup targets, choice configuration, indexed-column
limits, unique-ID support, webhook regression tests and rollback views in a test
site. No inventory JSON, credentials or tenant-specific IDs belong in Git.

