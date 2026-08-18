# EDN Systems OS — Universal Work Capture V1

Status: Repository implementation complete; live Microsoft activation not authorised
Increment: `UWC-001`
Canonical contract: `1.0.0`

## Outcome

Universal Work Capture is one fast entry path for meaningful billable work and
non-billable work with operational or technical value. The existing **Work Log**
is the physical source of truth. Projects, Actions, evidence libraries,
Engineering Knowledge, summaries, billing preparation and Daily Intelligence
consume a stable Work Capture reference; they do not receive copies of the same
work facts.

This increment implements the source-neutral domain contract and projection
planner locally. It performs no Microsoft authentication, live data access,
SharePoint mutation, deployment or external execution.

## Repository reality reconstructed

| Finding | Consequence for Work Capture |
|---|---|
| SharePoint is the current operational database and UI | Keep the production record in Microsoft 365; local code defines and validates the contract |
| `Projects` is the populated authoritative project register; `Project Register` is an empty competitor | Select from `Projects`; create no new project register |
| `Actions` is populated, authoritative and webhook-connected | Create a follow-up only when explicitly requested, with a Work Capture source key; do not create another action queue |
| `Work Log` is approved as authoritative work evidence | Extend/bind Work Log as the canonical Work Capture store rather than creating `Work Captures` plus a duplicate Work Log row |
| `Project Files` is the intended project-document system and is webhook-connected | Store files there or in a confirmed evidence library; Work Log stores references only |
| `Engineering` and `Engineering Knowledge` are separate, populated, versioned and webhook-connected | Working artifacts remain in Engineering/Project Files; only human-marked candidates project to Engineering Knowledge as drafts |
| Existing IMS rules require stable IDs, explicit provenance, human authority and evidence by reference | Work Capture uses a client UUID, stable capture ID, payload hash, applied-profile version, native audit fields and append-only corrections |
| Current Work Log fields, exact Work Log GUID, Power Apps definitions and Power Automate definitions are not available in Git | The SharePoint contract remains logically bound and fail-closed until a separately authorised current dependency review resolves exact IDs and fields |

The exact Assets GUID in the IMS manifest is unrelated and is not reused. No
tenant-specific Work Log, Projects, Clients or Actions GUID was invented.

## Final V1 phone journey

The recommended interface is a standalone, responsive **Power Apps canvas app**
using the existing SharePoint structures and two narrow Power Automate flows.
The ordinary path is one screen:

1. **Project** — recent project preselected; selecting a project loads client,
   work type, billing, rate class, evidence and photo-policy defaults.
2. **What happened?** — one large multiline field; phone keyboard dictation is
   usable immediately. V1 stores the resulting text as a human-entered fact and
   does not require AI.
3. **Confirm** — large duration chips and outcome chips; date defaults to today,
   signed-in engineer is automatic, and start time is optional.
4. **Evidence** — shown only when required or requested. Photo controls are
   absent when prohibited. A required artifact that is not yet available marks
   the capture `pending`; it never prevents the work fact from being saved.
5. **More** — collapsed panel for billing/task code overrides, follow-up,
   knowledge-candidate note and corrections.
6. **Submit** — returns `Saved`, `Saved — evidence pending`, or an explicit
   retained-on-screen failure. It never reports success before the canonical
   Work Log item is confirmed.

Target interaction for a normal job with defaults:

```text
Project (2–4 s) → summary/dictation (8–15 s) → duration/outcome (4–7 s)
→ submit (2–4 s) = approximately 16–30 seconds
```

Evidence upload adds the file picker and transfer time. The capture itself is
saved first so an upload failure cannot erase the entered work.

## Canonical event

The canonical `WorkCapture` is a human-fact event with a typed envelope. It is
implemented in `src/edn/work_capture` and is independent of Power Apps,
SharePoint and any future voice interface.

### Always required at acceptance

| Concept | Rule |
|---|---|
| Capture identity | `WC-<submission UUID>`; the UUID is generated once on the device and reused for retries |
| Project | Stable project ID and source reference from the selected active project profile |
| Engineer | Authenticated Microsoft identity, represented by a durable principal ID |
| Work date | Defaults to the current local date; must not be later than capture time |
| Duration | 1–1,440 minutes; large UI chips avoid typing |
| Summary | Plain text, whitespace-normalised, maximum 500 characters |
| Work type | Explicit or project default |
| Outcome | Explicit or project default, normally `completed` |
| Billing treatment | `billable`, `non_billable`, or `review_required`; explicit or project default |
| Rate class | `standard`, `scheduled_after_hours`, `night`, or `other`; it supports later commercial rules without storing an invoice |
| Applied policy | Project profile version, secure-site flag, photo policy and evidence requirement |
| Provenance | Capture method, app version, capture timestamp, `human_confirmed`, defaulted-field list, revision and payload hash |

### Defaulted

- client from project, where the project has a client;
- signed-in engineer from the app identity;
- work date from the device-local current date;
- work type, outcome, billing treatment, rate class and billing code from the
  selected project profile;
- evidence requirement by `(project, work type)` with a project fallback;
- secure-site and photo policies from the exact project profile version; and
- capture method and app version from the entry point.

The event records which values were defaulted. This makes fast entry auditable
without pretending that the engineer typed every value.

### Conditional

| Condition | Additional fact/rule |
|---|---|
| Project requires a task/reference code | `task_reference` is mandatory |
| Engineer selects follow-up | Follow-up summary is mandatory; due time and owner remain optional |
| Evidence is required but absent | Capture is accepted with `evidence_status=pending` and appears in an evidence-pending view |
| Evidence is supplied | One or more typed HTTPS/URN references; no binary body is stored in the event |
| Photo policy is `prohibited` | Any handoff-photo reference fails before submission |
| Photo policy is `restricted` | A photo requires a durable authorisation reference |
| Engineer marks technical value | A concise knowledge note is recorded; summary becomes the note only when the engineer intentionally selected `candidate` |
| Capture corrects an earlier event | New capture ID, revision greater than one, `supersedes_capture_id` and correction reason are mandatory |

### Optional

Client (for internal/operational work), work start time, billing code, task
reference, follow-up due/owner, evidence references, photo authorisation,
technical note and correction lineage.

### Deliberately absent

- invoice amount, tax and invoice state;
- a hard-coded hourly rate (the current commercial rate belongs in a future
  approved rate schedule, referenced by billing/rate classification);
- binary files or base64 content;
- autonomous AI inference in human fact fields;
- automatic action creation where the engineer did not request follow-up;
- automatic promotion to approved Engineering Knowledge; and
- destructive edit-in-place correction behavior.

## Evidence and secure-site behavior

Evidence requirement and photo permission are independent:

| Evidence requirement | Photo policy | Behavior |
|---|---|---|
| Required | Prohibited | Require a non-photo artifact such as VIAVI result, configuration file or commissioning record; hide camera/photo controls |
| Required | Restricted | Accept non-photo artifacts immediately; require an authorisation reference for a photo |
| Required | Allowed | Offer file/photo capture; save canonical work first and report upload state |
| Optional/not required | Any | Keep evidence panel collapsed unless the engineer opens it |

An `EvidenceRef` contains only stable reference ID, kind, HTTPS/URN locator,
optional file name and optional SHA-256. The locator rejects credentials and
secret-like query parameters. Source permissions still govern access; a link
does not grant permission.

## Idempotency, audit and failure behavior

1. The app creates one UUID when the entry starts and retains it through retries.
2. Work Log enforces uniqueness on capture ID and submission key.
3. The accept flow searches by submission key before create.
4. The same key and same facts returns the existing success receipt.
5. The same key with different facts fails as an idempotency conflict. If a
   cryptographic hash cannot be implemented using an approved native component,
   the flow compares every immutable human-fact field rather than accepting an
   undocumented hash function.
6. Downstream create-once projection IDs are deterministic from capture ID,
   destination and projection version.
7. SharePoint Created/Author/Modified/version history remains native audit
   evidence. The canonical event also records capture method and profile version.
8. Corrections append a new capture and point to the superseded capture. V1 does
   not silently overwrite the original work fact.
9. File upload occurs after canonical acceptance. A failed upload changes the
   visible state to evidence pending and offers retry; it does not roll back or
   hide the saved capture.
10. If canonical create fails, the app retains all inputs in memory/on screen,
    disables duplicate taps while the request is active and shows a retryable
    error. It does not clear controls or claim success.

SharePoint-backed offline queuing is deliberately not enabled in V1. Microsoft
documents built-in offline-first support for Dataverse, while SharePoint
connectors are not supported by that mode. `SaveData`/`LoadData` could store a
small custom queue in Power Apps Mobile, but that would put client work facts on
the device and require an approved mobile-data, conflict, retention and wipe
policy. Online-with-explicit-failure is the safer first release.

## Downstream relationship model

| Destination | Mode | V1 rule |
|---|---|---|
| Work Log | Canonical owner | One accepted event or append-only correction; no projection copy |
| Project activity/history | Reference | Filter Work Log by stable project ID and link to capture |
| Actions | Idempotent create-once | Only for explicit follow-up; action stores projection key and source capture reference |
| Evidence & Test Results | Reference/backlink | Capture stores evidence state and references; evidence record/file stores capture ID backlink |
| Project Files | Reference/backlink | Binary remains in library; file metadata points to capture/project |
| Engineering Knowledge | Idempotent draft candidate | Only when human marks technical value; it remains draft until reviewed |
| Weekly work/timesheet | Derived view | Group canonical date, engineer, duration, project and billing classification |
| Billing preparation | Derived view | Include billable/review-required captures; rate schedule and invoice remain separate future authority |
| Daily Intelligence | Authorised read reference | Retrieve canonical capture under existing source/domain/classification controls |

Every `create_once` target must enforce the deterministic projection key. A
retry that finds the same key and source hash is success; a key/hash mismatch is
a visible conflict. Derived views never write values back to the source event.

## 400G synthetic demonstration

Input summary:

> 400G test completed. FEC enabled at remote end, clean test after configuration correction.

Project defaults apply testing, completed, billable, standard rate class,
`SYNTH-400G`, secure site, required test evidence and prohibited photographs.
The resulting event is accepted with 120 minutes and `evidence_status=pending`.
It receives stable ID
`WC-b06f89a8-f836-42d6-87df-4af8c245dbad` and produces reference/derived
intents for project history, weekly summary, billing preparation, evidence,
Project Files, Daily Intelligence and a human-marked Engineering Knowledge
candidate. It does **not** create an Action because no follow-up was requested.

Run it locally:

```bash
PYTHONPATH=src /home/elliot/.venvs/edn-os/bin/python \
  -m edn.work_capture.cli \
  tests/work_capture/fixtures/400g-test-pending.json
```

Adding a VIAVI `test_result` HTTPS reference changes evidence status to
`complete`. Adding a `handoff_photo` fails because the applied project policy is
`prohibited`.

## Microsoft product basis

The recommendation follows current Microsoft behavior documented in:

- [responsive canvas-app layouts](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/create-responsive-layout);
- [running canvas apps in Power Apps Mobile](https://learn.microsoft.com/en-us/power-apps/mobile/run-powerapps-on-mobile);
- [Power Apps attachment-control limits](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/controls/control-attachments);
- [triggering Power Automate and adding files to cloud storage](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/how-to/trigger-flow);
- [Power Apps (V2) file input to a SharePoint document library](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/how-to/pdf-function); and
- [Power Apps offline behavior and limitations](https://learn.microsoft.com/en-au/power-apps/maker/canvas-apps/offline-apps).

The built-in attachment control is not used on Work Log because Microsoft binds
its upload/delete behavior to a list or Dataverse form. That would store binary
attachments on the canonical list item, contrary to the reference-only evidence
contract.

## Repository artifacts

- `src/edn/work_capture/`: typed contract, validation, canonicalisation, stable
  payload hash and projection planner;
- `tests/work_capture/`: field-rule, security, idempotency, correction,
  projection and CLI tests plus synthetic 400G fixture;
- `config/work-capture-v1-sharepoint-contract.json`: unbound logical SharePoint
  field/destination contract; and
- `docs/work-capture/`: Power Apps build specification and exact activation
  boundary.
