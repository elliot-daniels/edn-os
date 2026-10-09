# Durable partial email drafts — synthetic prerequisite

Missing manual-required information must not discard a genuine job request.
EmailDraftStore therefore retains incomplete source-bound drafts separately from
canonical reviewed Work Intake requests. It has no approval/export or external
action methods and does not weaken manual fields or approval hashes. No existing
request-store schema changes or migrations are performed.

The public service composes a storage-only adapter to reuse the existing
IntakeStore protected SQLite snapshot connection, rather than duplicating raw
file/SQLite protections. The small private subclass changes schema validation
and initialization only; inherited request operations are not exposed. Linux/WSL
and a private Linux filesystem remain mandatory. Locks, safe publication,
owner-only modes, symlink/hardlink checks, sidecar refusal and snapshot limits
remain the existing protection implementation. Native Windows refuses before
creating storage; Windows test success proves that refusal, not Linux behavior.

Each receipt retains original source fields and source identity/hash. Local Event
UUID/import time and AI overlays are excluded from source replay comparison.
Exact replay retains answers/history; changed content under the same source key
fails closed rather than overwriting the original. Source bodies remain protected
runtime data, never Git/CI artifacts. Pilot limit is 1,000 receipts and the existing
100 MB metadata snapshot limit. Initialization is explicit; read-only access does
not create missing stores. No retention deletion exists.

Answers require an exact revision and actor, retain previous answers and original
facts, distinguish operator-confirmed values, and survive reopening. Concurrent
answers cannot lose a revision. Missing questions answered by the operator are
removed from the outstanding view. Financial/general/uncertain messages cannot
receive new-job continuation answers. Corrupt assessments are isolated with an
explicit queue diagnostic count.

This prerequisite does not yet link an incomplete draft into the complete manual
request model, download email attachments, resolve forwarded/thread duplicates,
approve source changes, produce reservations, infer durations or render the mobile
queue. These are required before complete unattended intake acceptance. The
existing Android demo remains unchanged. Independent exact-head Grok QA/Dot and
full hosted Linux/Windows gates are required before integration. Synthetic-only
storage does not establish owner approval for either real email or cloud hosting
of real email.

N51-01 state-preserving upgrade is addressed with explicit assessment versioning.
Legacy unversioned receipts remain readable/replayable with original data, answers
and history intact, but are flagged stale and cannot accept continuation until
audited reassessment. Explicit synthetic reassessment increments revision and
retains the previous assessment in history. It never resets/deletes data and
refuses non-synthetic sources. Current version validation remains strict; changing
the classifier requires a version decision rather than silently invalidating
retained drafts. Real-store reassessment remains a separate owner gate.
