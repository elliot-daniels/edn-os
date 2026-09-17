# Proposed one-shot V2 morning briefing — NOT AUTHORIZED OR EXECUTED

Prepared 17 September 2026. The previous successful category-only pilot is
complete. Its authority is consumed; this proposal is a new owner decision.
The earlier activation proposal remains the historical V1 boundary and is not
silently rewritten by this document.

## Prerequisites before new approval

Review `EMAIL-ADMISSION-V2.md` and the resulting repository commit. Supply a
minimal fresh owner-verified relationship manifest: exact sender addresses and/or
project codes, stable entity keys, checked times and supporting `EvidenceRef`
provenance in the approved EDN domain/classification. Clients and Projects must
declare their coverage, including unavailable. Optional EDN contact/Actions
sources follow the same contract. Do not invent entries, harvest senders from
the pilot mailbox, or label an incomplete contact sample as a complete source.
Schema inspection alone cannot supply verified operational relationships.

Record and approve the manifest hash and resulting `email-admission-v2:<digest>`
authority in a frozen local execution manifest alongside the exact repaired
native-to-internal resource mappings. Review the actual match rules, not a generic
promise to use V2. An incomplete source cannot authorize relationship matches;
category-only fallback remains possible but will disclose relationship uncertainty.
The smallest useful V2 pilot needs at least one usable independently verified
relationship source. No live relationship manifest exists as a result of this
synthetic session. Constructing an arbitrary snapshot does not authorize it.

## Frozen proposed boundary

| Item | Boundary |
|---|---|
| Tenant | `aae6ab79-45eb-4829-a04f-595becdb936d` |
| Existing public client | `2381e4f6-44bc-4697-ad64-e86513cb9dee` |
| Delegated identity | `elliot@ednsystems.com.au` |
| Existing scopes | `User.Read`, `Mail.Read`, `Calendars.Read`; no additions/consent |
| Invocation | Exactly one manual attempt using a new run marker; no retry/schedule |
| Account resolution | `/me?$select=id,userPrincipalName,mail` |
| Mail source | Only that account's Inbox, resolved through `/me/mailFolders/inbox?$select=id,displayName` |
| Email window | Received time from execution instant minus seven days through execution instant |
| Email cap | At most 25 metadata records before admission; one page; no continuation |
| Admission | Reviewed V2 exact policy/snapshot authority; category or fresh verified exact relationships; no fuzzy/AI scoring |
| Calendar | Only resolved default calendar of that account; unchanged EDN category boundary |
| Calendar window | Today through next seven calendar days in `Australia/Adelaide`, using existing tested calendar window semantics |
| Calendar cap | At most 25 metadata events before admission; no continuation |
| SharePoint | Does not participate. No site/schema/item access; operational Projects/Clients/Actions remain unavailable |
| Provider | None |
| Output | One briefing/audit bundle in the approved local private folder; never Git/cloud sync |
| Retention | Maximum seven days from new artifact creation; no automated deletion service |

Mail projection exactly:
`id,parentFolderId,subject,from,toRecipients,receivedDateTime,lastModifiedDateTime,importance,isRead,categories,webLink`.

Calendar identity projection remains:
`id,name,canEdit,owner,isDefaultCalendar`.
Calendar event projection remains:
`id,subject,start,end,organizer,attendees,location,isAllDay,recurrence,webLink,lastModifiedDateTime,categories`.
No bodies, previews, MIME, attachments, new fields, other mail folders, mailbox
import, additional calendars or operational lists. No `conversationId` expansion.

Use the existing owner-approved private location:
`C:\Users\Admin\Documents\Codex\2026-09-14\files-pasted-by-the-user-edn\pilot-private\fresh-1795deae-20260917`.
Before authentication, revalidate ordinary create/write/read/delete/nonexistence
access with one harmless unique temporary file. Preserve the owner-established
ACL without broadening it. Freeze distinct new artifact names/run marker and an
absolute UTC deletion deadline. Do not overwrite existing artifacts or extend
their retention; in particular, the original stopped pilot's deadline remains
23 September 2026 09:15:46 UTC. Do not persist tokens or passwords.

## Required actual path, audit and stopping rules

Verify configured application, authenticated account, token tenant and existing
scope/consent before source retrieval. Resolve Inbox/default-calendar only,
preserve exact native IDs and deterministic EDN authority IDs, then evaluate the
new exact V2 permission scope through the registry/policy/MorningBriefApplication.
Interactive sign-in is performed by Elliot, never by collecting his password.

Produce one cited briefing plus its required JSON/run-store/audit artifacts.
Report separately: requested cap/window, pre-filter Microsoft count, admitted
count, included count, category/relationship reason counts, rejected/unavailable
decisions, duplicates/conflicts, returned cap/possible truncation, checked times,
relationship source freshness/completeness and all coverage gaps. Include policy
and manifest identities, native/internal mappings, actual artifact paths/hashes,
retention deadline and zero Microsoft-write/provider-call counts. The cap bounds
what was checked; no admitted evidence never proves nothing requires attention.
Do not invent citations for rejected or unavailable mail. No operational-list
facts may be inferred from a relationship-only owner manifest.

Stop before retrieval if identity/application/tenant differs, new consent is
needed, scopes must expand, the exact reviewed policy/manifest is missing or has
changed, source identity cannot be mapped, or storage controls fail. Unavailable
sources must be disclosed by the existing application; do not repair a live
security/access incompatibility in place or start another attempt. Stop after
this one attempt, successful or unsuccessful, and report for owner review.

## Exact proposed owner approval prompt

> Authorize ONE new manually invoked read-only EDN morning briefing using the
> reviewed Email Admission V2 commit and the exact owner-verified relationship
> manifest/policy digest frozen in the local execution manifest. Follow
> MORNING-BRIEF-V2-PILOT-PROPOSAL.md exactly. Use tenant
> aae6ab79-45eb-4829-a04f-595becdb936d, existing application
> 2381e4f6-44bc-4697-ad64-e86513cb9dee and elliot@ednsystems.com.au; verify identity,
> existing consent and protected local storage before retrieval. Read at most 25
> Inbox metadata messages from the previous seven days, without pagination, using
> the eleven frozen fields and the reviewed V2 manifest. Read at most 25 default
> Calendar metadata events for today through the next seven Adelaide calendar
> days using the unchanged projection and EDN category rule. Record native and
> EDN internal resource identities, all admission reasons, provenance, counts,
> caps, freshness and gaps through the actual policy/registry/morning application.
> Retain only this pilot's necessary protected local artifacts for at most seven
> days; preserve all older deadlines. No SharePoint, UWC, bodies, MIME, attachments,
> Microsoft writes, sends, provider calls, permission changes, consent, mailbox
> import, recurrence, deployment, merge or PR. Stop on a new technical/security
> incompatibility and stop for owner review after the single attempt. Do not retry.

This proposed prompt is not actionable until the actual commit and approved
manifest/digest are frozen and reviewed. No live execution is part of this session.
