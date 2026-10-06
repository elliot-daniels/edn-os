# Malformed legacy migration diagnostics

Explicit initialization still rejects malformed legacy Events and rolls back the
entire schema/identity backfill transaction. Valid neighbors processed before a
malformed row remain unchanged; no partial registry or schema version is published.
No source rows are repaired, quarantined, dropped or otherwise rewritten.

JSON, byte-decoding and Event-construction failures expose only the fixed
`Legacy Event payload cannot be migrated` diagnostic in normal exception tracebacks.
The underlying source-bearing exception chain is suppressed. This is a diagnostic
boundary, not an authorization to migrate real stores or inspect exception objects
with traceback locals. Indexed/provenance mismatches keep their existing fixed
messages and rejection behavior.

Synthetic regression checks cover invalid JSON, byte encoding, excessive nesting,
container/field types, source-bearing timestamp errors, indexed mismatches, exact
source-row/database-byte/schema/version rollback, valid migration and the public
init-command diagnostic. This evidence-backed subset does not claim full resolution
of F16-1 while its original detailed QA wording remains unavailable. Rollback is
reverting this scoped diagnostic change; source data and schema contracts are intact.
