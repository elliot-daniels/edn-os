# Event filter and snapshot consistency

SQL selects and orders Events using stored identity, timestamp, action and link
columns. Every decoded row now checks those columns against its JSON snapshot
before exposing the Event. Strict reads and replay reject mismatches; diagnostic
Inbox reads count and omit them within the existing bounded page. No row is
repaired by a read and no payload content enters diagnostics.

This aligns reading with the existing migration consistency checks. Filter option
discovery remains a distinct-column query: an invalid row may contribute an option,
but cannot render as a valid Event when that option is selected. Global validation
or quarantine is outside this bounded change. No schema change or triage overlay.
Rollback: revert this change; snapshots and database schema remain unchanged.
