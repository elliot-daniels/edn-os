# Audited synthetic email cancellation

`EmailDraftStore.cancel_job` accepts only a current synthetic cancellation draft.
It holds the existing draft-then-request lock order, obtains a bounded complete
canonical snapshot, validates every row and verified alias linkage, and requires
one non-terminal, source-resolved reference/customer/site match. Ambiguity, missing
fields, malformed rows, stale assessments/revisions or real-source inputs fail
closed. It rechecks target revision/hash while holding the same request lock.

Cancellation retains fields, attachments, original email and existing history,
increments the canonical revision, invalidates approval/delivery and records a
normal local-operator audit event with timestamp, revision/content hash and the
immutable cancellation source key/hash. Exact source replay returns the durable
cancelled result without adding another audit or revision. Interrupted publication
can be retried through the same source binding; no new schema/table is introduced.

This is a synthetic API orchestration prerequisite, not a mobile automatic
executor or live customer authority. Embedded sender headers are unverified.
An already-cancelled target from a different source requires review rather than
being cancelled again. Rejected, pending-source and ambiguous work also requires
review. Reservation release is not atomically coupled yet and remains an explicit
full-workflow blocker. No real event, email, SharePoint write or external AI occurs.

Linux/WSL local synthetic UI launch remains
`python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`,
then `http://127.0.0.1:8502`. Use a new private 0700 Linux parent outside Git and
`umask 077`; native Windows fails closed. Cancellation API is not wired to the
mobile UI. The existing accepted Android host remains unchanged. Independent
exact-head Grok/Dot review and full hosted CI are required before accepted
development integration; main/live-data/deployment authority remains pending.
