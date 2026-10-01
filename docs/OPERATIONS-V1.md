# EDN Operations Inbox v1

Operations is a small additive local activity store and UI. It uses the existing
Python/SQLite/Streamlit stack and the existing GET-only Graph transport/token
boundary. It does not migrate archived email memory, change the website intake,
or expand Power Apps/Power Automate. The user-authorized scope is in `NOW.md`.

## Event contract and replay

`edn.operations.models.Event` carries source, source account, native external ID,
aware occurrence/creation timestamps, direction, type, parties, subject, plain
body, attachment metadata, optional client/project/job IDs, optional derived AI
summary/actions, needs-action status, raw source payload and a local UUID.
Supported types: email, job_request, sms, whatsapp, call, voicemail, note,
job_update. Only email ingestion is implemented in this phase.

SQLite `operations_events` is isolated from the memory database. A unique
`(source, source_account, external_id)` constraint makes concurrent/restarted
replays first-write-wins: return the existing Event, retaining its original ID,
creation date, body and raw payload. Local sources must supply a durable external
ID (for example a note UUID); content-only deduplication would merge distinct
legitimate activity. No cross-mailbox deduplication is performed.

Outlook requests use immutable Graph IDs so folder moves within a mailbox do
not change identity. See [Microsoft immutable ID guidance](https://learn.microsoft.com/en-us/graph/outlook-immutable-id).
Mail retains internetMessageId, folder and webLink in raw provenance. Bodies are
requested and rendered as plain text. Attachment metadata is retained; binaries
are not downloaded. AI fields remain empty unless supplied by a caller. No
source data is sent to AI.

## Run locally

Use an approved encrypted runtime data root outside Git. Create the database
parent directory first. Install the repository development dependencies with
`pip install -e ".[dev]"` in your Python environment.

PowerShell example (replace mailbox and Microsoft app values):

```powershell
$env:EDN_OPERATIONS_DB = 'E:\EDN OS\Data\Databases\operations.db'
$env:EDN_DATA_ROOT = 'E:\EDN OS'
python -m edn.operations.cli init

$env:EDN_MS_TENANT_ID = '<existing EDN tenant ID>'
$env:EDN_MS_CLIENT_ID = '<existing Microsoft app client ID>'
$env:EDN_OPERATIONS_MAILBOXES = '<business-mailbox@domain>'
python -m edn.operations.cli ingest-outlook --auth delegated `
  --start '2026-10-01T00:00:00+10:00' --end '2026-10-02T00:00:00+10:00'

streamlit run src/edn/ui/app.py --server.address 127.0.0.1 `
  --browser.gatherUsageStats false
```

The default delegated mode reuses `DeviceCodeCredential`, requests User.Read
for identity verification and Mail.Read for content, and permits only the signed-in
business mailbox. Mixed personal/business mailboxes are not supported: configure
dedicated business accounts. Tokens are not persisted.

For multiple business mailboxes, `--auth application` reuses the website's
`EDN_MS_TENANT_ID`, `EDN_MS_CLIENT_ID`, `EDN_MS_CLIENT_SECRET` configuration with
MSAL. Set `EDN_OPERATIONS_MAILBOXES` to explicit comma-separated business
addresses. An existing SharePoint permission does **not** imply mail access.
Application Mail.Read and Exchange mailbox restrictions must already be approved
and configured; this code grants no permissions or modifies Microsoft settings.
Do not store secrets or source content in the repo.

If an account belongs to another tenant, run a separate authenticated import
with that tenant's approved app/account and only its mailbox addresses, pointing
at the same Operations database. The unified store keeps mailbox provenance
separate; a token for one tenant does not grant mail access in another tenant.

The legacy Outlook projection remains metadata-only; the shared transport now
rejects redirects and caps response bytes.
Operations has a separate explicit content-read client. Every mail request is a
GET scoped to a configured mailbox Inbox, with a bounded window of at most 31
days and up to 100 pages of 50 messages. Continuations must remain on the same
Graph host and mailbox resource. Default transport rejects every redirect before
following it, and bearer headers are excluded from urllib redirect copying.
Each response is read with a 1,048,576-byte cap plus one overflow byte; oversized
responses stop before persistence. A page with more than 50 records is rejected
before any record on that page is inserted, even when its response is small.
Attachment metadata must be a list/tuple of nonempty objects containing only
id/name/contentType/size/isInline/@odata.type; string, nonnegative integer size
and boolean inline types are checked. Binary/unknown fields are rejected.
Event serialization revalidates mutable nested metadata before database access;
decoding rejects corrupt historical metadata safely in the read-only Inbox. Failed records are counted without bodies in
logs; page exhaustion/malformed records yield `complete=false` and nonzero exit.
Network failure stops the command; already committed Events are replay-safe.
Narrow the window and replay if a run reaches the page limit. There is no
background scheduler, delta synchronization or automatic backfill yet.

## Inbox behavior and limits

Operations Inbox is the default page and needs only `EDN_OPERATIONS_DB`.
Email memory remains available through the page selector with its existing
configuration. The Inbox opens an existing database read-only, never initializes
missing files, and shows the latest 100 matching Events with source and
needs-action filters. Client/project/job filters appear only when Events have
those links. These are opaque IDs, not an invented CRM; no automatic relationship
resolution is attempted.

Needs action is an Outlook follow-up flag snapshot at first import, not unread
status or an AI guess. Event content is immutable on replay, so later flag/body
changes are not synchronized. Manual triage and source-update reconciliation are
future work. No outgoing email, attachment opening or external action is provided.

## Acceptance checks

Synthetic tests cover all Event types, persistence/replay, account isolation,
query safety, ordering/filtering, read-only behavior, paginated Graph reads,
unsafe continuations, bounds/failures, provenance and Streamlit interaction
without email-memory configuration. Existing Outlook tests guard the prior
metadata-only boundary. Live ingestion requires mailbox configuration and an
authenticated mail-read session; synthetic success does not claim live activation.
