# Universal Work Capture V1 — bounded test activation proposal

Status: **prepared for owner review; no Microsoft 365 mutation authorised or
executed**.

This proposal is bound to
`config/work-capture-v1-activation-manifest.json` SHA-256
`ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca`.
The manifest was re-hashed on 18 August 2026 and matched exactly.

## Proposed boundary

| Item | Proposal |
|---|---|
| Operator | `elliot-owner` |
| Environment | Existing EDN Systems Microsoft 365 tenant/site |
| Type | Bounded Universal Work Capture V1 test activation |
| Window | Owner-selected after this proposal is approved |
| Data | Synthetic/non-customer captures only; no billable or production records |
| Scope | One phone-friendly canvas app, minimum acceptance flow, optional evidence flow, and only approved optional Work Log fields |
| Explicit exclusions | No historical migration, no changes to Projects/Clients/Actions/finance data, no column deletion/rename, no webhook changes, no rate-rule changes, no offline queue |

Work Log remains the canonical physical source of truth. `ProjectLookup` and
`ClientLookup` are canonical relationships; legacy text `Project` and `Client`
are not used for V1 identity. Existing `RateCode` choices remain unchanged.
`Hours` remains intact and is converted to canonical integer minutes in the
capture/projection layer. Project Files is the V1 binary evidence destination.

## Exact Work Log field plan

New fields are optional at SharePoint schema level and required only in the app
where the contract says `required_in_app`. Existing fields are mapped without
renaming, deleting, or changing requiredness. “Hidden” means hidden from the
normal mobile form; the acceptance flow may write the value.

| Display name | Internal name | SharePoint type | Req. | Default | Index | Purpose | Status | Mobile | Rollback implication |
|---|---|---|---|---|---|---|---|---|---|
| Work Capture ID | `WorkCaptureID` | Text | app | — | yes* | Stable `WC-…` identity | new | hidden | Leave dormant; no destructive removal |
| Work Capture Submission Key | `WorkCaptureSubmissionKey` | Text | app | — | yes* | Retry/idempotency key | new | hidden | Leave dormant |
| Work Capture Schema Version | `WorkCaptureSchemaVersion` | Text | app | `1.0.0` | no | Contract version | new | hidden | Leave dormant |
| Project | `ProjectLookup` | Lookup | app | — | existing yes | Canonical Projects relationship | mapped existing | visible | No schema change |
| Work Capture Project ID | `WorkCaptureProjectID` | Text | app | — | no | Stable project ID snapshot | new | hidden | Leave dormant |
| Client | `ClientLookup` | Lookup | optional | project default | existing no | Canonical Clients relationship | mapped existing | progressive | No schema change |
| Work Capture Client ID | `WorkCaptureClientID` | Text | optional | — | no | Stable client ID snapshot | new | hidden | Leave dormant |
| Engineer | `Engineer` | Person | app | current operator | no | Work performer, distinct from Author | new | visible/defaulted | Leave dormant |
| Work Date | `WorkDate` | DateTime | app | today | existing yes | Work date | mapped existing | visible/defaulted | No schema change |
| Work Started At | `WorkStartedAt` | DateTime | optional | — | no | Optional start timestamp | new | hidden/progressive | Leave dormant |
| Duration Minutes | `DurationMinutes` | Number | app | — | yes* | Canonical integer duration | new; maps from `Hours` | visible | Leave dormant; retain `Hours` |
| Work Type | `WorkType` | Choice | app | `Field Work` | no | Operational category | mapped existing | visible/defaulted | No schema change |
| Work Summary | `WorkSummary` | Note/plain text | app | — | no | Concise human-confirmed summary | new; `TechnicalSummary` may be source mapping | visible | Leave dormant |
| Outcome Status | `OutcomeStatus` | Choice | app | — | no | Completed/partial/blocked outcome | new | visible | Leave dormant |
| Billing Treatment | `BillingTreatment` | Choice | app | project default | no | Billable/non-billable treatment | new; derives from `Billable` | visible/defaulted | Leave dormant; do not alter finance logic |
| Rate Class | `RateClass` | Choice | app | project default | no | Future commercial classification | new; do not replace `RateCode` | progressive | Leave dormant; no rate rules |
| Billing Code | `BillingCode` | Text | optional | project default | no | Future billing reference | new; existing `RateCode` remains | hidden/progressive | Leave dormant |
| Task Reference | `TaskReference` | Text | conditional | project default | existing no | Job/task reference | mapped existing | progressive | No schema change |
| Follow-up Required | `FollowUpRequired` | Boolean | app | false | no | Explicit follow-up decision | new | visible | Leave dormant |
| Follow-up Summary | `FollowUpSummary` | Note/plain text | conditional | — | no | Follow-up detail | new | progressive | Leave dormant |
| Follow-up Due | `FollowUpDue` | DateTime | optional | — | no | Optional due date | new | progressive | Leave dormant |
| Evidence Requirement Applied | `EvidenceRequirementApplied` | Choice | app | project default | no | Applied evidence rule | new | hidden/progressive | Leave dormant |
| Evidence Status | `EvidenceStatus` | Choice | app | `not_required`/`pending` | no | Evidence lifecycle | new | visible/progressive | Leave dormant |
| Evidence References JSON | `EvidenceReferencesJson` | Note/plain text | optional | — | no | Reference-only evidence links | new; binary prohibited | hidden/progressive | Leave dormant |
| Technical Value | `TechnicalValue` | Choice | app | — | no | Knowledge value classification | new | visible/progressive | Leave dormant |
| Technical Note | `TechnicalNote` | Note/plain text | conditional | — | no | Knowledge candidate context | new; `TechnicalSummary` remains | progressive | Leave dormant |
| Secure Site Applied | `SecureSiteApplied` | Boolean | app | project profile | no | Records applied security profile | new; derives from Projects | hidden | Leave dormant |
| Photo Policy Applied | `PhotoPolicyApplied` | Choice | app | project profile | no | Allowed/prohibited/authorised policy | new; derives from Projects | hidden/progressive | Leave dormant |
| Photo Authorization Ref | `PhotoAuthorizationRef` | Text | conditional | — | no | Required only for restricted authorization | new | hidden/progressive | Leave dormant |
| Capture Method | `CaptureMethod` | Choice | app | `mobile_app` | no | Phone/form/dictation provenance | new | hidden | Leave dormant |
| Source App Version | `SourceAppVersion` | Text | app | test build ID | no | Client provenance | new | hidden | Leave dormant |
| Captured At | `CapturedAt` | DateTime | app | server time | no | Acceptance timestamp | new | hidden | Leave dormant |
| Project Profile Version | `ProjectProfileVersion` | Text | app | resolved profile | no | Default provenance | new | hidden | Leave dormant |
| Fact Origin | `FactOrigin` | Choice | app | `human_confirmed` | no | Human fact vs later inference | new | hidden | Leave dormant |
| Defaulted Fields JSON | `DefaultedFieldsJson` | Note/plain text | app | `{}` | no | Audit of defaults | new | hidden | Leave dormant |
| Work Capture Revision | `WorkCaptureRevision` | Number | app | `1` | no | Append-only revision | new | hidden | Leave dormant |
| Supersedes Work Capture ID | `SupersedesWorkCaptureID` | Text | correction | — | no | Correction lineage | new | hidden | Leave dormant |
| Correction Reason | `CorrectionReason` | Note/plain text | correction | — | no | Human correction reason | new | hidden/progressive | Leave dormant |
| Work Capture Payload Hash | `WorkCapturePayloadHash` | Text | app | computed | yes* | Deterministic integrity/idempotency evidence | new | hidden | Leave dormant |

`yes*` denotes a proposed index/uniqueness safeguard to confirm during the
mutation plan; it is not an instruction to alter an existing index in this
proposal. Exact SharePoint choice values must be frozen in the owner-approved
implementation plan before mutation. No field outside the validated contract is
proposed.

## Smallest Power Platform scope

### Required for first usable capture

1. One standalone responsive canvas app: **Universal Log Work — V1 Test**.
   Screens: project/client selection, short summary, time/outcome, conditional
   follow-up/evidence, and confirmation. It uses read-only Projects/Clients
   lookups and submits one Work Log event.
2. One narrow acceptance flow: **UWC-AcceptCapture-v1**. It validates the
   submission key, creates exactly one Work Log record, records the payload hash,
   and returns a success/failure response. Retries must be idempotent.

### Useful but optional for test activation

- **UWC-AddEvidence-v1**: writes a synthetic file to Project Files and stores a
  reference/backlink only after the capture exists.
- **UWC-ProjectCapture-v1**: resolves project defaults and secure/photo policy;
  this can initially be performed in the app using read-only lookups.
- Explicit Actions projection for a follow-up, if the first test requires it.

### Deferred beyond V1

Engineering Knowledge draft projection, Evidence & Test Results projection,
weekly/billing summaries, Daily Intelligence, dictation, offline queue, invoice
automation, and any changes to unknown existing apps/flows.

No existing app or flow is modified because definitions were unavailable during
discovery. Existing webhooks remain untouched.

## Connections, permissions and licensing

The live review did not expose app packages, flow definitions, connector
configuration, or permissions. The activation owner must therefore confirm:

- the operator can read Projects and Clients and create Work Log records;
- the app/flow maker connection can use SharePoint against the existing site;
- Project Files write permission is granted only if the optional evidence flow is
  approved;
- the tenant has the applicable Power Apps canvas and Power Automate licensing
  for the selected connectors; and
- no broader permission or unattended credential is introduced.

These are prerequisites, not assumptions or approvals.

## Synthetic acceptance sequence

1. Submit one synthetic billable Field Work capture.
2. Verify one Work Log record, canonical lookups, minutes conversion, provenance,
   and payload hash.
3. Resubmit the same submission key; verify no duplicate record.
4. Submit an explicit follow-up and verify the action behaviour without touching
   production Actions data.
5. Resolve a synthetic secure/no-photo project profile; verify photo upload is
   blocked and policy provenance is recorded.
6. Submit a capture whose evidence is pending; verify the capture saves before a
   file exists.
7. Upload/reference one synthetic test result in Project Files and verify the
   capture backlink/reference.
8. Submit a correction; verify a superseding revision is created and the prior
   record is not overwritten.
9. Verify existing finance views and webhook health where observable without
   production records or webhook changes.

No customer data, genuine evidence, invoicing effect, historical migration, or
production workflow automation enters this test.

## Rollback and safety

- Disable/remove the test canvas app and test-only flows if acceptance fails.
- Leave optional new SharePoint fields dormant; do not destructively remove them
  during rollback.
- Clearly identify synthetic Work Log records and Project Files artifacts for
  controlled cleanup only under a later explicit approval.
- Never delete, rename, revert, disable, or rewrite existing Work Log, Projects,
  Clients, Actions, finance fields, views, webhooks, or libraries.
- Preserve all existing `Hours`, `RateCode`, invoice fields, lookup columns and
  version history.

## Risk assessment and unresolved dependencies

| Risk | Control |
|---|---|
| Unknown existing apps/flows | Standalone app/flows only; dependency review before any shared-resource change |
| Duplicate submissions | Submission key, payload hash and idempotent acceptance flow |
| Finance contamination | Synthetic non-production data; no rate or invoice changes |
| Secure-client photo breach | Project profile policy check before attachment; Project Files only |
| Schema rollback complexity | Optional fields left dormant; no destructive rollback |
| Permission/licensing mismatch | Owner confirms connections and licensing before activation |

## Exact owner GO wording

> GO — I approve the bounded Universal Work Capture V1 test activation described
> in `docs/work-capture/M365-TEST-ACTIVATION-PROPOSAL.md`, bound to manifest
> `config/work-capture-v1-activation-manifest.json` SHA-256
> `ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca`. The
> operator is `elliot-owner`; the activation window is [OWNER TO INSERT]. Scope
> is the existing EDN Systems site, synthetic/non-customer test captures only,
> one standalone responsive canvas app, the named minimum acceptance flow, and
> only the listed optional Work Log fields/mappings. No customer or historical
> data, billable/invoice effect, rate-rule change, offline queue, existing app or
> flow modification, webhook change, permission broadening, deletion, rename,
> migration, or production deployment is approved. Project Files is the only V1
> binary evidence destination. Stop immediately before any out-of-scope action
> or if the manifest hash, resources, permissions, or test boundary differ.

Until that exact GO is supplied with a concrete window and confirmed connection
permissions, activation status remains **BLOCKED**.
