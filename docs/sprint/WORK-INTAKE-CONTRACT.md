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
