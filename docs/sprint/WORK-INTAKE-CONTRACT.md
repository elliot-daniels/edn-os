# Local Work Intake contract and rollback

Grounded in elliot-daniels/edn-systems-website commit
`f2f91d415e57d8ec017bf6ddad481d30c2a3c50d`: `lib/job-request/types.ts`,
`schema.ts`, `providers.ts`, and `docs/microsoft-graph-sharepoint-job-intake.md`.
The existing form fields, limits, service and urgency choices are preserved.
PreferredDate is omitted when blank. Date validation additionally rejects invalid
calendar dates rather than preparing a Graph request that cannot be accepted.

SharePoint fields are Title (Pending), ContactName, Company, Email, Phone,
Site_x002f_Location, ServiceRequired, optional PreferredDate, Urgency,
JobDescription, CustomerReference, Source, SubmittedAt, ContractVersion (1.0),
and Status (New). Manual entry truthfully uses Source `EDN OS Manual`; the public
website provider uses `EDN Systems Website`. The inspected repository does not
establish live acceptance of the manual Source value. No Microsoft permission,
credential, site/list configuration or actual submission is introduced here.

Local requests use UUIDs, never fake EDN-JR IDs. The latter is assigned by the
website only after Graph returns an item ID and the Title update succeeds. Export
is approval-gated dry-run JSON only, records dry_run status, and never claims
Synced. No transport/client/token interface exists. Attachments remain local and
are excluded from the website field payload because its current contract has no
upload flow.

Explicit initialization creates a separate local SQLite request database schema
version1; no Event store migration or adoption occurs. Revisions are appended
transactionally. Exact revision approval is bound to a hash of normalized fields
and attachment metadata. Edits append a revision and invalidate approval/export
status. Optimistic revision checks under BEGIN IMMEDIATE prevent stale concurrent
edit/approval/export. Read-only and missing-store reads never initialize storage.
Unknown schemas and malformed persisted workflow state fail closed with fixed
errors. Queue pages are bounded and allow callers to inspect the entire queue.

Rollback disables Work Intake and preserves its local database for owner-led
recovery; source Events and website code are untouched. This synthetic MVP is not
production activation and establishes no live SharePoint compatibility claim.


## Owner-selected protected MVP storage and approval

Only Linux/WSL protected storage is supported. Native Windows refuses before any
runtime root or database create/modify operation. Existing absolute owned private
0700 roots and regular owned0600 single-link database/sidecar files are required;
symlink ancestry, hardlinks and unsafe ancestry permissions fail closed. Shared
request locks use owned0600 flock files. Runtime roots are selected explicitly;
this code does not grant production access or modify permissions on existing data.

The single local operator may explicitly self-approve. The visible audit stores
local UID with label `local operator (self-approval)`, exact revision, content hash,
UTC timestamp and decision in an append-only table. Editing invalidates current
approval but retains previous decisions. Attachments are at most20,000,000bytes
per file and100,000,000bytes aggregate per request, without arbitrary ten-file cap.
This revised pre-merge MVP schema rejects earlier synthetic lookalikes rather than
silently adopting an unaudited store; no real-store migration has been performed.


Backend evidence verification is mandatory before approval/export whenever the
request carries attachments. Configure the protected evidence root explicitly.
Completed quota receipts, exact metadata association, file bytes/hash and supported
format signatures must all validate; absent or stale evidence fails closed.
Queue diagnostics isolate malformed rows without permitting corrupt direct exports.
Hidden Unicode formatting and control characters are rejected, with CR/LF allowed
only in descriptions. Every edit records a local operator audit decision, including
explicit approval invalidation when applicable.

Linux directory operations are descriptor-relative after an owned no-follow
component walk. Under a private anchored flock, bounded ordinary SQLite snapshot
bytes are loaded with stdlib deserialize into an in-memory SQLite connection.
Successful writes serialize to a completely fsynced private pending snapshot and
publish with descriptor-relative atomic replacement; readonly query_only sessions
never persist. Initial publication is no-clobber. SQLite never opens a disk pathname
or infers ownership from descriptor numbers. DB metadata is bounded to100MB;
evidence bytes stay separate. Missing stdlib snapshot primitives fail closed.
Failed transactions and pre-publication failures preserve the original snapshot; process termination
before publication leaves only a private unconfirmed pending file. Existing active
WAL/journal stores require owner-led recovery rather than automatic adoption.
Linux roundtrip, concurrent/restart, failure and parent/final-name replacement tests
remain mandatory hosted evidence before acceptance. No real-store migration occurs.


Snapshot publication is the commit point. A directory fsync failure after atomic
replacement is an uncertain commit, not a rollback guarantee; reload determines
the actual durable revision before retrying. No destructive reverse rename is
attempted. Pending files before publication remain unconfirmed private recovery
artifacts. The backend accounts every physical request folder and all receipt
entries, rejecting orphans, incomplete reservations and inconsistent quota sizes.
Native Linux mount identity is verified; DrvFs/9p and unsupported filesystems are
refused even when metadata presents private modes.

| From | Permitted target/action | Reason/audit |
|---|---|---|
| draft | approved; rejected; cancelled; edited draft | approve explicit; rejection/cancel need bounded reason |
| approved | edited draft; rejected; cancelled | edit invalidates approval; terminal decisions need reason |
| rejected | reopened draft | bounded reopening reason |
| cancelled | none | terminal, source/revisions retained |

Creation records entered_by local UID, UTC instant, first revision and content
hash. All transitions append revisions/audits; source facts and previous approval
history remain intact. Exports itemize unconfigured/unverified live prerequisites
and carry a truthful contract target descriptor, never fabricated tenant/list IDs.
