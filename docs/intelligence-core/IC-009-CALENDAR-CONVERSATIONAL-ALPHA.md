# IC-009 Calendar + Conversational Alpha

## Architecture

```text
Streamlit Intelligence tab
  -> IntelligenceRequest (principal, purpose, domain, classification)
  -> Capability Registry + Permission Evaluator
  -> balanced bounded adapters
       Email Memory | Knowledge Graph | Microsoft 365 Calendar
  -> ContextEvidence + Core EvidenceRef
  -> structured priorities and labelled statements
  -> authority-bound follow-up session
```

The Microsoft Calendar connector implements the IC-003 Connector SDK and exposes
only `discover`, `search`, and `verify`. Its manifest declares
`calendar.discover`, `calendar.read`, `calendar.search`, and `calendar.verify`,
all requiring delegated `Calendars.Read`. There is no `act`, create, update,
delete, ingest, or sync capability.

## Graph and authentication boundary

`GraphCalendarClient` is injected into the connector. Automated tests use an
in-memory client and make no network calls. The live implementation uses the
Microsoft OAuth device-code flow, holds the delegated access token in memory,
does not cache credentials, and sends only GET requests. Graph field selection
excludes event body/description content.

Authentication proves Microsoft identity but does not create Core authority. A
Core `CapabilityUseDecision` bound to principal, purpose, domain,
classification, operation, and exact calendar/window scope is required before a
`ConnectorRequest` can be constructed.

## Event and evidence model

`CalendarEvent` retains native event/calendar identity, subject, timezone-aware
start/end, timezone, organizer, permitted attendees, location, all-day state,
bounded recurrence status, source URL, last-modified timestamp, categories,
security domain, and classification. It deliberately has no body field.

The Calendar evidence adapter converts an event into source-neutral
`ContextEvidence`. Its Core `UniversalRecordRef` identifies the source record;
the `EvidenceRef` locator retains the event timeframe and transformation version.
Graph objects never enter `IntelligenceService`.

`CalendarRetrievalResult` keeps only three aggregate observations about the
bounded Graph page plus admitted records. `pre_filter_count` is the number of
Graph event objects received before local category admission. `admitted_count`
is the number converted to EDN/EDN Confidential `CalendarEvent` records.
`rejected_count` is their difference. Rejected Graph objects are not retained in
the result and therefore cannot be converted into `EvidenceRef` or rendered by
the UI.

## Time and security boundaries

Supported windows are `today`, `next-7-days`, `this-week`, and `last-7-days`.
Bounds use the configured `Australia/Adelaide` timezone; timezone is tenant/source
configuration, not a Core default.

Two source modes exist:

- `dedicated-edn`: requires an owner-approved calendar used only for EDN; or
- `category-required`: admits only events carrying one exact approved category.

IC-009 proposes `category-required` with category `EDN` for the default mailbox
calendar. Uncategorized and differently categorized events are discarded before
evidence creation. A wrong-domain request cannot produce a usable Core authority
decision and therefore cannot reach Graph.

## Context and response behavior

Each adapter has its own evidence limit. The assembler orders evidence within a
source by score, then uses deterministic round-robin selection across source
families. Stable context IDs are deduplicated and the total context remains
bounded.

The deterministic response contains:

- labelled FACT, INFERENCE, RECOMMENDATION, and UNKNOWN statements;
- structured priorities with title, rationale, evidence, timeframe, confidence,
  recommended next step, and missing information;
- source-family coverage;
- capability gaps returned from Registry decisions; and
- private evidence separate from global knowledge.

It does not claim completeness. Calendar and historical email/knowledge still do
not establish current finance, accounting, SharePoint action, or project-register
state.

## Streamlit and sessions

The existing Search, Ask EDN, and Knowledge views remain. A new first-position
Intelligence tab adds chat input, structured priorities, labelled response text,
expandable evidence, source family, provenance timeframe, domain/classification,
and capability gaps. The Calendar capability appears as authentication-required
until separately approved and configured.

Streamlit retains the in-memory `IntelligenceService` and session ID across
reruns. Follow-ups retain the original principal, purpose, domain, and
classification boundary; a change fails closed. A final UI-side filter validates
domain and classification again before evidence is rendered.

## Validation and limitations

Synthetic tests cover Connector SDK conformance, no write capability, bounded
Adelaide windows, mixed-context filtering, authorization before Graph, event and
provenance serialization, Calendar adapter output, source-family balancing,
follow-up isolation, capability gaps, and UI evidence filtering. Live
authentication is explicitly deferred to the separate approval pack.

IC-009A additionally proves 5/2/3, 5/0/5, and 5/5/0 pre-filter/admitted/rejected
scenarios; exact case-sensitive category matching; and absence of rejected-event
content from the protected validation report.

The local Streamlit principal remains a single-owner asserted context rather than
a production authentication system. Category quality is human-maintained. There
is no durable Calendar cache/sync or durable conversation store in this Alpha.
