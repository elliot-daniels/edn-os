# Universal Work Capture V1 — Power Apps Build Specification

Status: Build specification only; 29-field Work Log schema exists; no acceptance flow, app submission path, or live V1 update

## Product choice

Build a standalone canvas app in a governed Power Platform solution, optimized
for Power Apps Mobile. Use a responsive vertical auto-layout, `Scale to fit=Off`,
large touch targets, accessible labels and the existing SharePoint sources.

A generated Microsoft Lists app or native list form is suitable as an emergency
fallback, but it is not the primary V1 experience. The target requires project
profiles, fast chips, conditional evidence, secure photo suppression, a
two-stage save, retry receipts and progressive disclosure. Those are a concrete
usability/control need for a small custom app, consistent with the IMS rule to
customize only when native forms do not meet the operating workflow.

## Screens

### 1. Capture

One scrollable screen with these sections:

| Order | Control | Initial state |
|---:|---|---|
| 1 | Project searchable combo | Most recently used active project; no stale inactive project |
| 2 | Project/client/policy strip | Read-only; client, billable state, evidence badge and `No photos` warning where applicable |
| 3 | What happened? | Large multiline plain-text input, auto-focus after project selection |
| 4 | Duration | 15, 30, 60, 90, 120 minute chips plus Custom |
| 5 | Outcome | Completed, Partial, Blocked; other values behind More |
| 6 | Evidence | Collapsed unless required; file/reference options filtered by photo policy |
| 7 | Follow-up / Knowledge value | Two compact toggles; their detail fields appear only when selected |
| 8 | More | Date/start time, rate class, billing code, task reference, alternate outcome |
| 9 | Submit | Full-width, at least 48 px high; disabled while request is in flight |

Do not show client as a second choice when the selected project supplies it.
Allow a no-client operational project/profile for valuable non-billable work.

### 2. Receipt

Show the stable capture ID, Work Log link and one of:

- `Saved`;
- `Saved — evidence pending` with `Add/retry evidence`;
- `Already saved` for a safe retry;
- `Conflict — this submission key already has different facts`; or
- `Not saved — your entry remains on this screen`.

Provide `Log another` and `Correct this capture`. Correction starts a new UUID,
sets revision and supersedes ID, and requires a correction reason.

### 3. My recent work

Read-only, bounded recent list for the current engineer. Each row shows project,
date, duration, outcome and evidence state. It links to the canonical Work Log
item and supports `Correct`, never direct destructive editing of fact fields.

## App state

Create `varSubmissionKey=Text(GUID())` and `varCapturedAt=Now()` once when
starting an entry. Do not regenerate either value on submit or network retry.
Clear them only after a confirmed canonical receipt or explicit user discard.

Project selection loads one versioned profile into `varProjectProfile`. The
submitted payload includes both stable IDs and the applied profile version. A
profile refresh must not silently change an in-progress entry; prompt the user
to reload if the selected version becomes stale before submit.

Use phone keyboard dictation as ordinary text entry. If a later speech service
is added, record `capture_method=voice_transcript`, preserve the human-confirmed
text, and keep any machine transcript/enrichment outside canonical facts until
confirmed.

## Submit flow: `UWC-AcceptCapture-v1`

Power Apps (V2) inputs are the canonical draft fields, submission UUID and
applied project-profile version. The flow:

1. authenticates as the invoking user and binds their identity as engineer and
   recorded-by; do not trust a display name sent by the client;
2. loads the exact active project/profile and rejects project/profile drift;
3. validates choices, duration, required conditions and photo/evidence policy;
4. canonicalises whitespace and serialisation ordering;
5. queries Work Log by unique submission key;
6. if absent, creates one Work Log event and returns the item reference;
7. if present, compares every immutable canonical fact (or an approved SHA-256
   calculated by a separately reviewed component): identical is `already
   saved`, different is `conflict`;
8. does not create downstream records in the acceptance transaction; and
9. returns a typed receipt before the app resets any input.

The flow's connection and run-only permissions must be solution connection
references. No owner-wide or tenant-wide generic write permission is implied.

## Evidence flow: `UWC-AddEvidence-v1`

Run only after a canonical receipt. Inputs: capture ID, project stable ID,
evidence kind, file name/content or an existing HTTPS/URN reference, and photo
authorisation reference when required.

The flow reloads the canonical capture and project policy, rejects prohibited
photos before file creation, writes the file to the confirmed Project Files or
Evidence & Test Results library, adds `WorkCaptureID` and project backlink
metadata, then appends/records the reference relationship and sets evidence
status to complete only when all required artifacts resolve. A failed transfer
leaves the capture at `pending` and returns a retryable receipt.

Use Power Apps (V2) `File` input and SharePoint `Create file`; do not use the Work
Log attachment column. Limit file count, type and size in approved configuration
and test actual VIAVI/configuration artifacts. Malware scanning, labels,
retention and client restrictions remain Microsoft/site policy controls and
must be confirmed during activation.

## Projection flow: `UWC-ProjectCapture-v1`

Trigger from an accepted canonical item, with trigger concurrency and retry
behavior tested. For each planned destination:

- derive deterministic projection ID from capture ID, destination and projection
  version using an approved implementation;
- query the target by projection ID before create;
- treat identical existing projection as success;
- stop and record a conflict if the key points to different source facts;
- never block or delete the canonical capture when a destination is unavailable;
- append a metadata-only projection receipt including attempt, status, target
  reference and error class; and
- never automatically approve knowledge, close work, accept risk or invoice.

V1 activation may initially enable only Work Log, project-history views and
evidence-pending views. Actions and Engineering Knowledge projections should be
enabled only after their observed webhooks and target fields pass regression.

## Offline decision

Do not store an offline queue in V1. A SharePoint-connected app cannot use the
built-in Dataverse offline-first mode. A custom `SaveData` queue would retain
client summaries and perhaps evidence on the device, has manual conflict logic,
and needs explicit classification, device-management, encryption, expiry and
remote-wipe decisions.

When disconnected, keep the in-progress record in app memory, show `Offline —
not saved`, prevent submit, and allow copy/discard under policy. A future offline
increment should use either an approved minimal encrypted text queue with no
evidence binary or a separately justified Dataverse architecture.

## Acceptance measures

- median normal capture at or below 30 seconds on the owner's actual phone;
- no more than project, summary, duration/outcome and submit for a default case;
- no photo control on a prohibited project;
- canonical item remains after evidence/projection failure;
- double-tap, timeout and flow retry create one canonical item;
- changed payload under the same key produces conflict, not overwrite;
- ordinary user cannot set another engineer or bypass project policy;
- corrections preserve the original and native version history;
- screen reader labels, contrast, focus order and touch targets pass review; and
- two representative billable and two valuable non-billable scenarios pass.
