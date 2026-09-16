# Morning briefing: activation proposal, not activation authority

Prepared 2026-09-16. No Microsoft tenant was contacted in this session. The
following identities come from local repository configuration and must still
match authenticated identity before any future read. UWC authority is separate.

## Smallest useful live pilot

One owner-invoked, read-only email/calendar briefing, with Projects/Clients/Actions
reported unavailable. No recurring schedule, background ingestion, AI provider,
or operational writes. This uses the existing PA-005 identity and category
boundary rather than authorizing an entire mailbox or site.

| Boundary | Proposed exact value |
|---|---|
| Entra tenant | `aae6ab79-45eb-4829-a04f-595becdb936d` |
| Public client application | `2381e4f6-44bc-4697-ad64-e86513cb9dee` (from `pa005_activation.py`) |
| Delegated execution identity | `elliot@ednsystems.com.au`; signed-in account and token tenant must match |
| Internal Core domain/tenant | `EDN` / `edn-local`, matching existing policy contracts |
| Mailbox | `/me`, authenticated as that exact account |
| Folder | Inbox only; resolve `/me/mailFolders/inbox` to its immutable ID and record it |
| Mail window | `[run time minus 7 days, run time]`, received-time instants |
| Mail limit/filter | At most 25 metadata records before local filtering; admit category `EDN` only; disclose that uncategorized/rejected/capped records are not covered |
| Calendar | That account's default calendar only; resolve and record exact ID before retrieval |
| Calendar window | Today through the next 7 calendar days, `Australia/Adelaide` to preserve PA-005; no ended event becomes upcoming |
| Calendar filter/limit | Category `EDN`; at most 25 records before admission |
| Future cadence | Candidate 08:00 `Australia/Adelaide`, disabled; owner must resolve Adelaide versus Sydney business-day preference before a recurring schedule |
| Permissions | Reuse existing delegated `User.Read`, `Calendars.Read`, `Mail.Read`; no consent or grant changes |

Mail fields requested by the existing GET-only client: `id`, `parentFolderId`,
`subject`, `from`, `toRecipients`, `receivedDateTime`, `lastModifiedDateTime`,
`importance`, `isRead`, `categories`, `webLink`. No body, MIME, attachments or
other folders. Account verification selects `id,userPrincipalName,mail`; Inbox
resolution selects `id,displayName`.

Calendar fields requested by the existing client: `id`, `subject`, `start`,
`end`, `organizer`, `attendees`, `location`, `isAllDay`, `recurrence`, `webLink`,
`lastModifiedDateTime`, `categories`. Identity resolution currently selects
`id,name,canEdit,owner,isDefaultCalendar` and retains only the default identity.
No event body or attachment. If owner prefers a narrower projection, reduce the
client's tested field contract before pilot execution, not silently during it.

The existing scopes are broader than these field projections. Microsoft also
defines basic mail/calendar and selected SharePoint permissions; adopting a new
permission model is a separate decision, not a reason to request consent here.
See [Microsoft permission reference](https://learn.microsoft.com/en-us/graph/permissions-reference).

## Minimal operational-list extension (not included in the first pilot)

Candidate site: `https://edn123.sharepoint.com/sites/EDNSystems`.
Historical local site GUID: `49cc1059-a4f6-42f7-88bd-9940503ae28f`; this is not a
verified composite Graph site identifier. Candidate list IDs from the local
contract inventory:

| List | Candidate ID | Semantic read projection |
|---|---|---|
| Projects | `66944251-b9a3-40cc-9a59-05538e200c19` | ID, Title/name, code only if distinct from title, status, client lookup ID, one approved deadline, Modified, ETag, classification field |
| Clients | `3d55c612-9799-4462-9474-7f0ca5a10b24` | ID, Title/name, Modified, ETag, classification field |
| Actions | `d7079aad-7f18-4164-8bd6-41f5629898bb` | ID, Title, status, due date, project/client lookup IDs, owner display identity, Modified, ETag, classification field |

Internal names and exact choice/lookup types are **not verified**. Do not use
the synthetic `Status`, `Due`, `Project` field names as live mappings. Long
descriptions, attachments, finance, documents and other fields are excluded.
Description is unnecessary where Title is sufficient. Lookup IDs must be
canonical identities, not display names. Configure only one reviewed project
and client relationship namespace; unresolved or conflicting relationships
become gaps.

The SharePoint connector remains a client protocol plus projection/validation
logic; it has no production HTTP client. A production client needs scoped
identity verification, explicit approved query semantics, bounded pagination,
typed transport failures, exact `$expand=fields($select=...)`, and synthetic
HTTP contract tests before activation. The source query must include the
approved open-action and active-project criteria, and related client identities;
keyword search alone cannot prove whole-list completeness. Start with at most
25 rows per list and record both pre-filter and admitted counts, continuation
and cap status. No whole-list opportunistic import.

The existing connector declares `Sites.Selected`. Reuse an existing exact-site
read grant if verified; this session did not inspect its presence or authorize
grant creation. List-specific selected permissions may provide a smaller future
boundary, but selecting or granting them needs separate review. Reference:
[Microsoft selected permissions](https://learn.microsoft.com/en-us/graph/permissions-selected-overview).

An owner-authorized **metadata-only** inspection of the exact candidate site and
three list schemas is the next SharePoint step. It must return identity, internal
column names/types and current principal grants, without reading operational
rows, consent, writes or UWC inspection. Then freeze a field/query/principal
manifest and obtain separate approval for operational reads.

## Storage, freshness and disable procedure

The local runner writes one SQLite run/audit store and a content-hashed JSON
brief containing admitted excerpts/provenance/coverage. This contains business
metadata when run live. Existing email databases remain read-only during
retrieval. Import status tracks last batch/terminal outcome; it never establishes
live inbox completeness. Legacy imports report unknown freshness. An import
older than one day is conservatively stale; a recent import is still a snapshot.

The first live pilot must select an owner-controlled local output directory
outside Git and sync folders, confirm its access controls, and agree retention
(proposed seven days, manual deletion after review). No background retention job
is installed. Existing POSIX protected-provider stores still fail closed on
Windows; this change does not make those stores Windows-compatible or authorize
provider use. The new local briefing output does not supply encryption or a new
ACL system. Do not claim production hardening from synthetic validation.

A successful checked source records its check time, counts and caps. Empty
results do not mean nothing needs attention; failures are sanitized gaps and
healthy evidence remains. Category rejection and source/context limits remain
visible. Neither a message's sent date nor a record's Modified date is treated
as the last successful synchronization time. The first pilot is a bounded
snapshot, not a complete mailbox or operational-list synchronization.

Disable by not invoking the local tick and removing the host's source
configuration; no OS task or cloud schedule exists to stop. Remove local pilot
artifacts under the agreed retention decision. If a future worker dies, stop
that process before explicit `recover_interrupted`, then retry. Never recover a
worker that may still be running. No permission revocation is needed to undo
this session because no permission changes were made.

## Exact proposed owner approval prompt

> Authorize one manually invoked EDN morning briefing pilot using tenant
> aae6ab79-45eb-4829-a04f-595becdb936d, existing client
> 2381e4f6-44bc-4697-ad64-e86513cb9dee, and delegated account
> elliot@ednsystems.com.au. First verify those identities and existing consent;
> stop if any identity differs, consent is required, or the local output access
> controls are unsuitable. Resolve and record only my Inbox and default-calendar
> identities. Read at most 25 Inbox metadata messages from the last seven days
> and at most 25 default-calendar metadata events from today through the next
> seven days in Australia/Adelaide, using the exact field projections and EDN
> category admission boundary in MORNING-BRIEF-ACTIVATION-PROPOSAL.md. Use the
> existing policy/registry and morning application, report pre-filter counts,
> rejected/capped/empty/unavailable coverage and freshness, and save the single
> cited result in an owner-controlled local directory outside Git and sync
> folders for up to seven days. No body/attachment retrieval, other mailbox,
> SharePoint operational reads, UWC access, writes, sends, provider calls,
> permission changes, consent or recurring schedule. Projects/Clients/Actions
> must remain explicit coverage gaps. Stop after the one result and report
> exact identities, read counts, output location and any failures.

This text is proposed future authority; it has not been executed.
