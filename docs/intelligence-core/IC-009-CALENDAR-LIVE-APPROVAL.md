# IC-009 Calendar Live Validation Approval Pack

Status: **DRAFT — NO LIVE AUTHENTICATION OR EXECUTION AUTHORIZED**  
Classification: EDN Confidential  
Prepared: 11 August 2026, Australia/Adelaide

## Purpose

Validate the IC-009 Microsoft 365 Calendar connector once using a bounded,
read-only retrieval. This approval does not authorize calendar mutation, Outlook
mail sync, SharePoint access, cloud AI, background synchronization, or external
action.

## Proposed exact scope

| Control | Proposed value |
|---|---|
| Operator/account | `elliot@ednsystems.com.au` |
| Microsoft tenant | `aae6ab79-45eb-4829-a04f-595becdb936d` |
| Public client application ID | `d08166f6-2074-4590-8edf-bb8275e9eb11` |
| Authentication | Interactive delegated device-code MFA; token held in memory only |
| Delegated permission | `Calendars.Read` only |
| Source | The account's Microsoft Graph default calendar endpoint |
| Event boundary | Only events carrying the exact Outlook category `EDN` |
| Security domain | `EDN` |
| Classification | `EDN Confidential` |
| Retrieval window | `this-week`, calculated in `Australia/Adelaide` |
| Maximum events | 25 |
| Event body | Excluded from the Graph field selection |
| Output directory | `F:\EDN OS\Working\Calendar IC-009\<approved-date>` |
| Output file | `calendar-live-validation.json` (must not already exist) |
| Git | Output must remain outside Git |
| Mutations | Zero; connector exposes no create/update/delete/action operation |

The category requirement is deliberate. A mailbox calendar may contain personal
and business entries; uncategorized and differently categorized entries are
excluded before becoming Core evidence. If the owner instead confirms a dedicated
EDN-only calendar, that is a material scope change and requires a revised command
and approval record.

## Data retained

The protected result contains the permitted event metadata: native event and
calendar identity, subject, start/end/timezone, organizer, permitted attendees,
location, all-day/recurrence flags, source link, last-modified time, categories,
domain, classification, and provenance. Calendar body/description content and
authentication tokens are not retained. Console output contains counts and paths,
not event details.

The report also contains:

- `pre_filter_count`: event objects returned by Graph from the already bounded
  calendar/time-window request, before exact-category admission;
- `admitted_count`: those objects admitted as EDN / EDN Confidential calendar
  evidence after exact category and security checks; and
- `rejected_count`: `pre_filter_count - admitted_count`.

Only admitted events appear in `events`. Rejected event identifiers, subjects,
attendees, locations, links, categories, or other content are not persisted.

## Exact proposed command

Run from `/home/elliot/projects/edn-os` in `/home/elliot/.venvs/edn-os` only after
the output directory exists, the output file does not exist, the repository
version/hashes are recorded, and the approved execution window is open:

```powershell
wsl -d Ubuntu-24.04 -- bash -lc 'cd /home/elliot/projects/edn-os && /home/elliot/.venvs/edn-os/bin/python -m edn.connectors.microsoft_calendar.cli validate-live --tenant aae6ab79-45eb-4829-a04f-595becdb936d --client-id d08166f6-2074-4590-8edf-bb8275e9eb11 --account elliot@ednsystems.com.au --calendar-id default --calendar-name "Default calendar (EDN category only)" --scope-mode category-required --required-category EDN --window this-week --limit 25 --output "/mnt/f/EDN OS/Working/Calendar IC-009/<approved-date>/calendar-live-validation.json"'
```

## Stop conditions

Stop without retrying or broadening scope if:

- the tenant, client ID, account, calendar endpoint, category, permission,
  timezone, window, output path, command, or tested source hash differs;
- consent requests any permission beyond delegated `Calendars.Read`;
- authentication cannot use the approved account and interactive MFA;
- the output file already exists or protected storage is unavailable;
- the connector attempts an event-body request or any mutation;
- events without the exact `EDN` category enter the result;
- the execution window is not open; or
- any domain/classification or provenance validation fails.

## Known limitations

- Category accuracy is human-maintained. Miscategorized EDN events will be missed;
  incorrectly categorized personal events could be included.
- Default-calendar metadata alone does not prove a complete view of EDN work.
- Calendar plus historical email/knowledge does not include current finance,
  project-register, SharePoint action, or accounting state.
- The live command creates a protected evidence file but no durable calendar sync.

## Consolidated GO request

Before execution, the owner should respond once with the following completed
approval record:

> GO — I approve one IC-009 read-only live validation using
> `elliot@ednsystems.com.au`, tenant
> `aae6ab79-45eb-4829-a04f-595becdb936d`, client application
> `d08166f6-2074-4590-8edf-bb8275e9eb11`, delegated `Calendars.Read`, the default
> calendar endpoint restricted to exact category `EDN`, EDN domain, EDN
> Confidential classification, `this-week` in Australia/Adelaide, maximum 25
> events, and protected output
> `F:\EDN OS\Working\Calendar IC-009\[approved date]\calendar-live-validation.json`.
> Event bodies, writes, mail sync, SharePoint access, cloud AI, background sync,
> and external actions are not approved. The report must show Graph pre-filter,
> EDN admitted, and rejected counts while retaining only admitted event records.
> Execution window:
> **[owner supplies date/time window in Australia/Adelaide]**. Stop on any scope,
> permission, hash, security, storage, or behavior discrepancy.

No authentication may begin until the execution window is supplied and this GO
is explicitly received.
