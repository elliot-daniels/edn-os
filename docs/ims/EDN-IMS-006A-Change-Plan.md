# EDN IMS-006A Controlled Metadata Change Plan

Status: Proposed; explicit subsequent GO required before live Apply  
Date: 2026-08-09  
Site boundary: `https://edn123.sharepoint.com/sites/EDNSystems`

## Safety boundary

IMS-006A adds optional metadata fields to existing authoritative structures. It
creates no lists, libraries, views, lookups, items, permissions, labels,
automation or retention settings. It changes no existing field, URL, webhook or
business record. The machine-readable source is
`config/ims-006a-fields.json`; its SHA-256 must be approved immediately before a
future Apply run.

The corrected IMS-003 inventory was used for list IDs, existing internal names
and webhook indicators. Permissions, content types, Power Platform definitions
and Purview configuration remain unknown.

## Exact proposed fields

All fields are optional and have no deployed default. IMS-006A performs no record
backfill. Indexing is a recommendation for a later
approved step because setting it would require an additional mutation command.

| Structure | Candidate internal fields | Type | Required/default/index | Reason and existing-record impact | Automation risk | Rollback | Deploy now? |
|---|---|---|---|---|---|---|---|
| Projects | `IMSRelevance` | Choice | false / none / recommended later | Scope flag; existing records blank | Webhook observed; contract unknown | Hide field | **No** — dependency evidence required |
| Clients | `IMSInformationClassification` | Choice | false / none / recommended later | Handling metadata; no reclassification | Webhook observed; contract unknown | Hide field | **No** — dependency evidence required |
| Actions | `IMSSourceType`, `IMSSourceRecordID`, `IMSSourceReference`, `IMSEffectivenessStatus` | Choice, Text, URL, Choice | false / none / indexes later | Provenance/effectiveness; existing records blank | Webhook observed; highest payload risk | Hide fields | **No** — dependency evidence required |
| Assets | `IMSAssetClass`, `IMSAssetOwner`, `IMSCriticality`, `IMSInformationClassification` | Choice, User, Choice, Choice | false / none / indexes later | Operational asset metadata; existing files blank and unchanged | No webhook observed; Power Platform remains unknown | Hide fields; retain data | **Yes** — exact live manifest |
| Approvals | `IMSDecisionType`, `IMSRationale`, `IMSSubjectType`, `IMSSubjectRecordID`, `IMSSubjectReference` | Choice, Note, Choice, Text, URL | false / none / indexes later | Decision provenance; existing decisions untouched | Webhook observed; authority-sensitive | Hide fields | **No** — dependency evidence required |
| Executive Metrics | `IMSDomain`, `IMSObjective`, `IMSTarget`, `IMSCalculationSource` | Choice, Note, Text, URL | false / none / indexes later | Objective/provenance; existing metrics untouched | Webhook observed; contract unknown | Hide fields | **No** — dependency evidence required |
| System Status | `IMSControlOwner`, `IMSEvidenceReference` | User, URL | false / none / indexes later | Monitoring ownership/evidence; existing state untouched | Webhook observed; monitoring-sensitive | Hide fields | **No** — dependency evidence required |
| Quotes | `IMSRequirementSummary`, `IMSAssumptions`, `IMSExclusions` | Note | false / none / no | Contract-review evidence; existing records blank | Webhook observed; workflow unknown | Hide fields | **No** — dependency evidence required |
| Engineering Knowledge | `IMSKnowledgeType`, `IMSTechnicalOwner`, `IMSReviewStatus`, `IMSSourceReference` | Choice, User, Choice, URL | false / none / indexes later | Knowledge lifecycle; documents untouched | Webhook observed; contract unknown | Hide fields | **No** — dependency evidence required |
| Work Log | None | — | — | Future fields require undeployed lookup targets | No proposed mutation | None | **No** |

The exact live manifest contains **4 optional fields on Assets only**. The other
24 otherwise-low-risk candidates are deferred rather than assuming webhook
compatibility. Work Log remains unchanged.

## Deliberately deferred fields

- All lookups to Risks, Controls, Obligations, Findings, Actions or Approvals.
- All 24 candidates on webhook-connected structures until the consuming
  contracts or an approved residual-risk decision establishes safety.
- Date fields requiring an explicitly validated SharePoint date format:
  `IMSRequirementsReviewDate`, `IMSDecisionReviewDate`, `IMSLastCheckDate`.
- Default values; the strict IMS-006A mutation path creates optional fields only.
- Stable IDs requiring record backfill (`IMSActionID`, `IMSApprovalID`).
- Authoritative Approval decision/state and closure fields.
- Metric threshold calculations.
- System Status control/finding lookups.
- Work Log IMS relationships.
- Quote risk/approval lookups.
- Engineering Knowledge control lookups.
- Client narrative requirement and assurance summaries pending semantics review.
- Any required, calculated, sensitive, retention-dependent or permission-dependent
  field.
- Index mutations. Recommendations remain in the manifest for later review.

## Dependency decision

Discovery proves webhook references on eight candidate structures but does not
expose their consuming contracts. Those candidates are excluded from the live
manifest. No webhook was observed on Assets, although unavailable Power Platform
definitions remain unknown. A future GO must include a matching live Plan and
explicit acceptance of that residual unknown. Existing automation is never
invoked, changed or redeployed by the tool.

## Deployment engine

`installer/Deploy-EDNIMS006A.ps1` separates the generic engine from EDN's JSON
manifest. It requires explicit site, client, tenant, manifest and output values;
uses interactive MFA; validates exact list GUID/title; compares internal
name/type/required/choices; and reports `would_create`, `already_compliant`,
`incompatible`, `created` or `failed`.

Plan uses only schema reads. Apply permits only `Add-PnPField`, refuses the whole
run on any incompatible field, and requires both an Approval ID and the approved
manifest SHA-256. Reports are sanitized, deterministic in ordering and
no-clobber. Neither mode enumerates items or exports business content.

## Rollback plan

No automatic rollback is supplied because deletion would be destructive and the
increment adds no views or automation. For a later approved rollback:

1. stop populating the affected field;
2. remove it from any subsequently approved forms/views;
3. hide/de-emphasize it using a separately approved additive configuration
   change; and
4. retain all field definitions and data for audit/recovery.

Field deletion, type changes and data clearing are prohibited.

## Commands for a future approved window

First calculate and record the manifest hash:

```powershell
Get-FileHash -Algorithm SHA256 `
  -LiteralPath ./config/ims-006a-fields.json
```

Read-only live Plan (still requires a separately approved authentication window):

```powershell
./installer/Deploy-EDNIMS006A.ps1 `
  -SiteUrl 'https://edn123.sharepoint.com/sites/EDNSystems' `
  -ClientId '<approved-client-id>' `
  -Tenant '<approved-tenant-id>' `
  -ManifestPath './config/ims-006a-fields.json' `
  -Mode Plan `
  -OutputDirectory '<approved-protected-no-clobber-output-directory>'
```

Exact Apply shape after a subsequent explicit GO and successful matching Plan:

```powershell
./installer/Deploy-EDNIMS006A.ps1 `
  -SiteUrl 'https://edn123.sharepoint.com/sites/EDNSystems' `
  -ClientId '<approved-client-id>' `
  -Tenant '<approved-tenant-id>' `
  -ManifestPath './config/ims-006a-fields.json' `
  -Mode Apply `
  -ApprovalId '<recorded-IMS-006A-approval-id>' `
  -ApprovedManifestSha256 '<approved-lowercase-sha256>' `
  -OutputDirectory '<approved-protected-no-clobber-output-directory>'
```

Placeholders must be replaced only from a recorded approval. This document and
the earlier discovery approval do not authorise either live command.

## Required GO package

Before Apply, record operator, approver, deployment window, protected pre/post
inventory and backup paths, manifest/script hashes, Plan report, dependency
review, expected `would_create` set, regression procedure, output classification,
retention and rollback owner. Any mismatch is an automatic NO-GO.
