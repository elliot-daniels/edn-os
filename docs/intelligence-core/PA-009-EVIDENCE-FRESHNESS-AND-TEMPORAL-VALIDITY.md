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

The 2026-08-17 UTC ledger admitted one initial attempt after the existing
Microsoft PKCE callback completed. Exactly one bounded Calendar/Inbox/protected
Local Files retrieval produced a 7-item, 1009-character metadata-only projection
at reference time `2026-08-17T09:10:11.301080+00:00`; all projected items were
explicitly provider-approved and carried derived temporal state. The protected
preflight hash was
`20e8d2d1754613f136dd138050741580c99a2aff6b55eb42301772dfa541c81c`.

The single OpenAI lifecycle returned HTTP 200 / `completed` and passed strict
schema, citation-membership and temporal semantic validation. The retained
owner-review result independently reloaded after dispatch with exact statement
typing, validated evidence IDs, uncertainty, proposal-only preservation,
integrity, expiry and owner-only permissions. Its proposal was a request for
proof confirmation, not an external action; no time-invalid preparation action
was generated. This genuine proof passes and PA-009 is provisionally ready for
routine bounded operation under existing controls. The durable audit and budget
ledger remain authoritative; no limits were changed.
