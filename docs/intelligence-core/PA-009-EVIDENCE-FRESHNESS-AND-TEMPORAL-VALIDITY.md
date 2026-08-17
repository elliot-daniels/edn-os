# PA-009 — Evidence Freshness and Temporal Validity

Status: repository implementation complete; synthetic validation passed. No
provider, live-source or credential access occurred in this increment.

## Closed temporal taxonomy

Every PA-009 projection is evaluated at one timezone-aware lifecycle reference
time and carries exactly one derived state:

- `future` — the trusted source time or calendar start is after the reference;
- `current_recent` — an event is active or timestamp age is within policy;
- `stale_historical` — inbox or file metadata is older than its bounded window;
- `expired_past_event` — a calendar end is strictly before the reference; or
- `unknown_undetermined` — trusted time metadata is absent, malformed, ambiguous
  or not covered by a declared source rule.

Retrieval time, item order and the old source-assigned freshness label cannot
make evidence current. Calendar uses its already-authorised start and end;
Inbox uses received/sent time with a seven-day recent window; Local Files uses
modified time with a 30-day recent window. Datetimes are compared as aware
instants, so UTC/Adelaide conversion and midnight rollover do not alter meaning.
Synthetic and genuine evidence follow identical rules.

## Projection and protected binding

`DisclosureProjector` derives temporal state after evidence admission and before
provider projection. The provider sees only the closed state and the single
reference time in addition to previously approved metadata; calendar temporal
boundaries are not newly disclosed. The reference and every item state are
included in canonical protected-envelope serialization and the preflight hash.
A genuine preflight without an aware reference time fails closed.

Protected-envelope and lifecycle audit metadata do not acquire source content,
event boundaries, evidence values or statement text. The protected owner-result
schema is unchanged.

## Deterministic response semantics

Strict schema and citation membership run before temporal validation. A statement
supported only by expired calendar evidence is rejected if it represents the
event as current/upcoming or proposes preparation/attendance before the elapsed
event. A proposal supported only by stale/historical evidence is rejected when
its explicit ISO-date deadline precedes the projection reference date.

Historical evidence remains admissible for retrospective statements and for
proposal-only follow-up on unresolved consequences. Mixed citations are not
silently rewritten; model output remains inference and never becomes verified
fact or execution authority.

The regression fixture reproduces retained-result request
`pa009-20260816T020321Z-167ee79cb599`: the 2026-08-13 event evaluated on
2026-08-16 is `expired_past_event`, and “Prepare before the 2026-08-13 meeting”
fails at the closed `temporal_semantics` validation stage.

## Security review

The review confirmed temporal derivation uses only already-admitted source
timestamps, adds no source permission or provider category, and adds no source
content to durable audit or retained results. Reference/state tampering changes
the protected hash. Unknown time fails closed, proposal-only semantics and
citation membership remain intact, and owner review still cannot cause external
action.

## Genuine retained-result proof status

The 2026-08-17 UTC durable ledger admitted a fresh initial attempt under the
unchanged limits. The approved environment-key mechanism passed a presence-only
check, but the separate Microsoft browser-PKCE flow was not completed within
either of two 600-second interaction windows. Both attempts stopped before Graph
or Local Files retrieval, provider projection, protected preflight creation, budget
reservation, OpenAI transport, or retained-result creation. Durable counters
therefore remained at zero requests, zero retries, zero successes and zero
estimated USD for the UTC day.

This is an authentication-interaction dependency, not a temporal-control pass or
failure. The genuine retained-result proof remains outstanding, and PA-009 has
not been promoted to routine bounded operation.
