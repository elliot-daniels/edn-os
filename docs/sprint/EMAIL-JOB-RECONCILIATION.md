# Synthetic existing-job reconciliation prerequisite

`match_email_job` consumes a synthetic Operations Event, its current deterministic
assessment and an explicitly complete canonical job snapshot. It returns a
proposal only. It performs no store writes, sends, calendar actions, provider
dispatch or live reads. PR #53's held review head is unchanged; this is independent
of the canonical materialisation and reservation implementation files.

New-job intent, updates and cancellations require all three reported identifiers:
customer, site and job reference. A reference alone cannot target another job.
Source quotes from forwarded/quoted history cannot supply current intent or match
facts under the existing assessment contract. Case, Unicode normalization and
whitespace differences can match; hidden/control characters cannot. Reported
identifiers are evidence, not customer authority or verified historical truth.

Incomplete/untyped coverage, missing facts, no match, multiple matches, terminal
jobs or unresolved source changes produce distinct hold statuses. Malformed rows
anywhere in the snapshot refuse reconciliation: ignoring one could hide another
target. The synthetic bound is 1,000 jobs. A caller must establish complete coverage
before passing `complete=True`; this flag is not an independently authenticated
store receipt. No-match new work remains a candidate, not an automatic creation.
Ordinary correspondence never selects a target or proposes a booking.

Unique matches bind the source Event identity, canonical UUID, current revision and
the existing Work Intake fields/attachment content hash. Replayed import UUIDs do
not change the proposal; forwarded source identities remain distinct while an
identical target is reused. A changed job produces a changed version/hash binding.

Future execution must reread the canonical store under its existing lock, verify
the bound revision/hash, perform audited mutation with approval invalidation and
update/cancel any associated provisional reservation. This pure function grants
none of that execution authority and does not itself deduplicate threads, preserve
a receipt, perform a cancellation or verify that an email sender is authorised.
Those remain full-workflow acceptance blockers, alongside attachments and mobile
orchestration. Do not claim unattended or live readiness from this prerequisite.

Tests independently cover unique update/cancel/new-work matches, replay, forwarded
identity, ordinary correspondence, reference-only and quoted-history refusal,
ambiguity, terminal/pending jobs, conflicts, malformed rows, stale/forged assessments,
coverage bounds and hidden characters. Pure tests run on Windows and Linux; this
change makes no claim of Windows protected-store support. Full hosted gates and
independent exact-head Grok QA/Dot acceptance are required before integration.

Rollback reverts this additive branch; no store, schema, credentials, permissions,
frozen QA files or existing runtime data are changed.
