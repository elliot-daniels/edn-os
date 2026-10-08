# Atomic Event import checkpoints

Tracked imports now commit each inserted/replayed Event and its record counters
in one SQLite transaction in the same explicitly selected database. Failure of
the checkpoint rolls back that record transaction, including identity mapping.
Error finalization uses committed outcome counters, rather than potentially stale
in-memory counters. Malformed records and completed-page checkpoints remain
explicit metadata-only progress; no completion is inferred from Events.

The outcome store refuses read-only or mismatched database pairs before source
access. Its externally supplied transaction must belong to that selected database
and already be active. Existing outcome schema/version/type checks remain.

A synthetic subprocess exits inside a checkpoint after its SQL update but before
commit: restart observes neither the Event nor its counter. Replay then imports
the Event once. Catchable termination handling is a separate PR. A hard kill can
still leave in_progress, correctly displayed as unconfirmed completion; no active
process/stale ownership guess, scheduler, schema migration or real import added.

This PR is stacked on Event index consistency. Rollback: revert this code; both
tables retain the existing schema, and source Events remain immutable.
