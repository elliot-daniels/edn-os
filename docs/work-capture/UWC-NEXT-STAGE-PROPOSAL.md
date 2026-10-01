# UWC next-stage proposal — acceptance-flow preparation

Status: **repository-only; prepared, not authorised, not executed**

Proposal: `UWC-002-ACCEPTANCE-FLOW-PREPARATION`

## Objective

Prepare the next reviewable Universal Work Capture stage: an idempotent boundary
between the existing **EDN Work Capture** canvas app and the existing **Work
Log**. This proposal creates no flow, changes no app, reads or writes no live
record, and grants no Microsoft authority.

The former `UWC-AcceptCapture-v1` creation window expired without execution. It
is closed and cannot be reused. Approval of this repository proposal is not an
approval to perform Microsoft work.

## Exact eventual resource boundary

| Resource | Bound identity | Intended role |
|---|---|---|
| Power Platform environment | `EDN Systems (default)` / `Default-aae6ab79-45eb-4829-a04f-595becdb936d` | Own the reviewed flow and existing app |
| SharePoint site | `https://edn123.sharepoint.com/sites/EDNSystems` / `49cc1059-a4f6-42f7-88bd-9940503ae28f` | Exact site boundary |
| Work Log | `7b6d10ec-c009-422a-9802-c907d3d4f57f` | Canonical accepted Work Capture store |
| Projects | `66944251-b9a3-40cc-9a59-05538e200c19` | Read-only project-profile reference |
| Clients | `3d55c612-9799-4462-9474-7f0ca5a10b24` | Read-only client reference |
| EDN Work Capture | `a47efc3e-0b52-405a-a220-54930a4ffdc9` | Human entry, retained retry key, receipt presentation |
| Proposed flow | `UWC-AcceptCapture-v1` (does not exist) | Validate, deduplicate, create once, read back and return receipt |

No Actions, evidence library, Project Files, Engineering Knowledge, finance,
rate, view, webhook, permission, production, or Intelligence Core mutation is
included.

## Intended acceptance architecture

The app generates one submission UUID and retains it across retries. A Power
Apps (V2) trigger sends `submissionKey` and `payloadJson` to the acceptance
flow. The flow validates the exact contract and reads project/client references.
It then queries Work Log by `WorkCaptureSubmissionKey` before any create.

- Same key and same immutable facts: return the existing receipt; create zero.
- Same key and different facts: return an idempotency conflict; mutate zero.
- No matching key: create exactly one Work Log item, read it back, and return
  `status`, `captureId`, item ID, item URL, evidence state and message.
- Ambiguous create result: stop. Perform a read-only recovery lookup before any
  retry.

The app must not create Work Log items directly. It retains entered values on
failure, prevents duplicate taps, and displays success only after a confirmed
flow receipt.

## Fields

The future flow may reuse `Project`, `Client`, `WorkDate`, `WorkType` and
`TaskReference`, and map the 29 optional fields already activated and recorded
in `config/work-capture-v1-sharepoint-contract.json`. It must not create the
dormant `WorkStartedAt`, `RateClass`, `BillingCode`, `TechnicalValue` or
`TechnicalNote` fields. This proposal authorises no schema change.

## Abort and rollback

Abort before mutation on any branch, hash, resource identity, connector,
permission, schema, idempotency, authority-window or environment mismatch. Only
standard Power Apps and SharePoint connectors are admissible; premium, custom,
HTTP and Dataverse paths are prohibited.

Repository rollback is a normal revert of the proposal commit. A future draft
flow must remain disabled and unconnected until separately approved. The 29
activated fields are not deleted. Potentially accepted Work Log records are
never deleted during recovery; reconciliation is read-only and corrections are
append-only.

## Validation and authority gates

Repository validation requires focused Work Capture tests, the full suite on
the supported POSIX runtime, Ruff, strict mypy, JSON parsing, frozen hash checks
and clean Git state. A later metadata-only Microsoft preflight requires its own
read authority.

Creating or saving the flow requires a **new explicit, time-bounded owner GO**
bound to the reviewed proposal commit/hash. Connecting the app, enabling or
running the flow, and performing a single synthetic acceptance test are later,
separate approval gates. The expired 2026-08-21 authority is not reusable.
