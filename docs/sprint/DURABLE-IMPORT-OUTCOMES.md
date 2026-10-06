# Durable bounded Operations import outcomes

The additive `operations_import_outcomes` table records each explicit Outlook
Inbox attempt with its own UUID, source/account, requested window, start/end time,
inserted/duplicate/rejected counts, completed-page count, state and fixed reason
code. Each row carries outcome schema version 1 independently of the Event schema
registry. Unknown outcome row versions fail closed. It contains no source bodies,
raw responses, tokens, exception strings or continuation URLs.

The CLI initializes the outcome table explicitly in an existing selected local
Event database. Existing Events are unchanged. `import-status` and the Inbox read
history with SQLite read-only mode; a missing legacy outcome table means never
run, and these reads create neither a database nor a table. Inbox shows the latest
recorded attempt per account within the 20 most recent attempts. It describes
complete, partial, failed, never-run and in-progress-or-interrupted states without
inferring coverage from existing Events or claiming entire-mailbox completeness.

A successful exhausted page sequence is complete only if no records failed.
Malformed records or the page cap produce partial outcomes. Exceptions before any
progress produce failed outcomes; exceptions after progress produce partial
outcomes. Source exceptions retain the API's original raised error, while the
CLI emits only sanitized durable metadata and continues separately scoped mailbox
attempts. No new auth, permission, scheduler or live-source behavior is added.

Counters are checkpointed after records and completed pages. An unhandled process
interruption leaves durable in-progress evidence with unconfirmed completion;
restart displays it as in progress or interrupted, never complete. Event insertion
and outcome checkpoints use separate commits, so a hard interruption between
those commits can leave checkpoint counts below stored Events. Retry remains
first-write-wins and reports duplicates, preserving Events and history. The
history does not store or reuse continuation URLs; retry starts the same bounded
requested window explicitly.

Synthetic tests cover complete/replay, malformed records, page caps, initial and
later failures, interrupted restart, metadata privacy, read-only legacy/missing
stores, CLI status and Inbox presentation. This is repository acceptance only;
real imports/storage approvals remain Elliot-controlled. Rollback removes the
new CLI/UI integration and outcome module while retaining both source Events and
additive outcome rows. No production data migration or deletion is performed.

Review controls additionally reject unsupported Event registry versions before
outcome writes or authentication, unknown/empty lookalike outcome table schemas,
coerced counter types, malformed identities/windows/timestamps, inconsistent
terminal states and intake counts beyond existing bounds. Synthetic checkpoint
interruption confirms that a committed Event may exceed the last durable counters
while history remains incomplete; replay reconciles by counting duplicates.

Inbox labels displayed counts as the recorded durable checkpoint. For an
in-progress/interrupted attempt, it explicitly warns that stored Events may
exceed those lower-bound counters; this does not imply confirmed completeness.
