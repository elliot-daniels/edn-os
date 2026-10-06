# Operations Event identity and schema foundation

Base: authoritative main `c85938c44ef230b5e4574b084d709f263b92adc0`.
This synthetic repository change does not authorize migration of a live database.

## Identity contract

`Event.identity_key` is `event-source-v1:` followed by SHA-256 of compact UTF-8
JSON containing exactly `[source, source_account, external_id]`. Source identifiers
are case-sensitive and are not normalized, concatenated ambiguously or derived
from body/content. Two databases observing the same tuple have the same stable
identity key. Different sources, accounts or native IDs remain independent.

Existing `Event.id` values are preserved as local references. They remain in every
payload and row, including existing UUIDs or caller-supplied IDs. Replay remains
first-write-wins for content, timestamps and local ID. A separate
`operations_event_identities` registry persists stable keys with unique local
Event references; the original ten-column Events table remains intact. No
content-only deduplication or local-reference rewrite occurs.

## Explicit schema initialization and migration

`PRAGMA user_version=1` identifies the Event schema foundation. An unversioned
legacy database can still be inspected read-only without mutation. Inserts into a
legacy database require explicit `EventStore.initialise()` (the existing `init`
CLI command); reads and ordinary writes never perform an implicit upgrade.

Initialization takes a SQLite immediate transaction. It checks known schema
shape/types/constraints, creates the identity registry, validates legacy payloads
against physical source identity and indexed fields, backfills identities and
publishes version 1 only when every row succeeds. It preserves Events byte-for-byte
and rolls back registry/schema/version changes on a malformed or mismatched row.
The caller receives a metadata-only failure and must resolve corrupt data through
an owner-approved recovery path; the code does not silently delete or rewrite it.
Repeated initialization is idempotent. An unrelated database is not adopted.
Future/unsupported versions are rejected before reads, writes or initialization.

No production migration was performed. To roll back development verification,
discard the synthetic migrated copy and return to the untouched original. Do not
change a database version marker by hand or run older code against a live upgraded
store; actual migration/recovery and merge remain owner decisions.

## Scope and validation

This branch adds identity/schema contracts only. It does not implement Inbox
malformed-row resilience, manual triage, import outcomes or new source adapters.
It overlaps those independent changes only at additive Event properties and
EventStore connection/initialization/insertion integration. Reconcile those small
areas and rerun focused/full checks when combining the PRs.

Synthetic tests cover stable identity across databases, source/account separation,
legacy ID/content preservation, restart/replay, concurrent replay, explicit upgrade,
read-only compatibility, future-schema rejection, malformed/physical-payload
mismatch rollback, constraint validation and atomic insert rollback. Validation
results are recorded in the PR. Hosted Linux runtime CI remains a required check;
Windows baseline failure allowances do not waive Linux security tests.
