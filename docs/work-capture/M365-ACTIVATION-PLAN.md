# Universal Work Capture V1 — Microsoft 365 Activation Plan

Status: Prepared boundary; stop before first authentication or mutation

## Authority boundary

Nothing in this repository increment authorises Microsoft sign-in, SharePoint
reads or writes, Power Apps/Power Automate creation, connector creation,
permission consent, solution import, deployment or use of live EDN/customer
data. The existing IMS discovery approval is historical and read-only; it does
not authorise this activation.

## Exact pre-activation request

Request one owner-approved **read-only dependency and schema review** for the
exact EDN Systems site. The approval must name:

- site URL, tenant, operator identity, client/application or connector identity,
  exact delegated read scopes and authentication window;
- exact structures: Work Log, Projects, Clients, Actions, Project Files,
  Engineering Knowledge and any candidate Evidence & Test Results destination;
- metadata only: object GUID/title/URL, fields/internal names/types/required/
  uniqueness, versioning, content types, views, permission shape, webhook/flow/
  app references, retention/label indicators and list thresholds;
- explicit exclusion of item values, document contents, file content, customer
  data, secrets and mutation;
- protected no-clobber output/backup paths, EDN Confidential handling,
  retention/disposal, hashes and reviewer; and
- the exact reviewed script/commit and stop conditions.

This is the minimum next authority needed. Reuse the existing inventory/export
patterns only after confirming they cover current Power Platform dependencies;
the prior discovery recorded Power Apps and Power Automate definitions as
unavailable.

## Repository-to-live binding sequence

### Gate 1 — resolve reality read-only

1. Run the separately approved current metadata/dependency review.
2. Bind every logical object and semantic field in
   `config/work-capture-v1-sharepoint-contract.json` to an exact existing GUID
   and internal name or mark it absent.
3. Confirm Work Log is still the authoritative work-evidence structure and that
   extending it does not conflict with its current field/automation contract.
4. Confirm how Projects currently relates to Clients and how Actions/Work Log
   currently relate to Projects. Reuse those fields rather than creating
   synonyms.
5. Confirm the physical evidence destination. If no suitable Evidence & Test
   Results library exists, use Project Files for V1 and retain evidence kind in
   metadata; do not create a new library by assumption.
6. Produce a field-level collision, webhook/app/flow impact and permission
   report. Unknown remains unknown.

### Gate 2 — prepare an immutable Plan

Generate an exact, machine-readable activation manifest with:

- site/list/library GUIDs and expected titles/URLs;
- existing-field reuse mappings;
- additive optional fields only, with types, choices, uniqueness/index plan and
  display/form treatment;
- no rename, delete, type change, required-on-populated-list, item backfill or
  permission widening;
- solution/app/flow names, owners, connection references and environment;
- test identities and synthetic test project/client values;
- pre/post inventory, backup, rollback/hide plan and regression checks;
- expected mutation count and exact scripts/tool versions; and
- canonical SHA-256 plus a no-clobber protected output path.

Run Plan in a non-production test site or isolated test objects first. The Plan
must refuse incompatible fields, missing GUIDs, title/GUID drift, unknown
dependencies, observed consumer failure, absent versioning, unsafe uniqueness or
unexpected permissions.

### Gate 3 — owner GO for exact test activation

The owner reviews the manifest hash, mutation set, connection scopes, Power
Platform solution, data classification, retention, evidence policy, mobile
device policy, licensing/cost, test window, operator and rollback. Approval is
bound to that exact hash and expiry. Any material change is a new decision.

Test activation order:

1. optional Work Log fields and unique submission/capture keys;
2. versioned project-profile fields or an approved configuration companion if
   changing Projects is unsafe;
3. Work Log views: My Recent Work, Evidence Pending, This Week and Billable
   Review;
4. `UWC-AcceptCapture-v1` with synthetic data;
5. responsive phone app with no evidence binary;
6. evidence backlink metadata and `UWC-AddEvidence-v1`;
7. project activity derived view;
8. observed webhook/app/flow regression tests;
9. Actions projection; then Engineering Knowledge candidate projection only if
   target regressions pass; and
10. monitoring, failure queue, owner acceptance and measured capture-time trial.

### Gate 4 — production GO

Require a new exact production manifest and approval after test acceptance.
Record pre-change inventory/backup, operator, approver, window, hashes,
connections, expected changes and rollback owner. Apply idempotently, collect a
post-change inventory, reconcile exact changes and run smoke/regression tests.

Rollback is non-destructive: stop new flows, remove app sharing/navigation,
hide newly added fields/views and retain canonical records/field definitions.
Do not delete fields, items, files, history or original evidence.

## Activation validation scenarios

1. Ordinary 30-minute billable project work with no evidence.
2. The synthetic 400G/FEC test with required VIAVI result and prohibited photos.
3. Required evidence upload times out after canonical save; capture remains
   visible as pending and upload retries safely.
4. Secure client: photo UI absent and direct flow attempt rejected.
5. Scheduled/night work uses a non-standard rate class without calculating an
   invoice.
6. Valuable non-billable operational work creates a draft knowledge candidate.
7. Explicit follow-up creates exactly one Action under flow retries.
8. Double-submit creates one Work Log record.
9. Same submission key with changed facts fails as a visible conflict.
10. Correction creates a new record linked to the original.
11. Inactive/mismatched project profile fails before mutation and preserves app
    inputs.
12. Destination failure never deletes or rewrites canonical work.

## Owner decisions that remain

Only decisions not safely derivable from repository evidence remain:

1. Approve the read-only current Work Log/Power Platform dependency review.
2. Confirm the evidence binary destination if no suitable current library is
   discovered; recommendation: use Project Files for V1 rather than create a
   new library.
3. Confirm whether offline storage is prohibited or should become a separately
   governed later increment; recommendation: no offline queue in V1.
4. Confirm later rate-schedule ownership and after-hours/night rules before
   invoice-ready money calculations; V1 records classification only.
5. Approve the exact test activation manifest, connections, licensing/cost,
   mobile distribution and evidence/mobile-data policy after the read-only
   review.

## Recommended next step

Prepare and approve the exact read-only dependency/schema review described in
Gate 1. Do not authenticate or mutate Microsoft 365 until that approval exists.
