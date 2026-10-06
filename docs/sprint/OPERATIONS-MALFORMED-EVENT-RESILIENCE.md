# Operations malformed Event resilience

The read-only Inbox now retains valid activity when another stored Event is
malformed. It reports the number omitted from the selected bounded page without
printing payloads or exception details. It reads at most 100 rows, including
omitted rows; it does not infer whole-store completeness from that page.

Event decoding validates identity, timestamps, parties, content, optional links,
actions and snapshot flags. Invalid records raise ValueError consistently.
Strict list_events and replay decoding still fail closed. Only the explicit
diagnostic read isolates individual malformed payloads. SQLite/schema failures
remain database errors. Source snapshots are never repaired or rewritten by
reading. No runtime migration, credentials, live reads or permission change.

Synthetic tests cover malformed collections/fields/JSON, valid neighbors,
bounded omission counts, UI warnings, database errors and byte-for-byte read-only
preservation. Rollback: revert this change; stored data and schema are unchanged.
