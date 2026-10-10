# Synthetic email drafts to canonical Work Intake jobs

`EmailDraftStore.materialise(source_key, expected_revision, requests)` creates a
normal Work Intake draft from a complete, current synthetic new-job assessment.
It holds the draft lock while publishing the canonical request. The request store
already retains the source receipt, so a crash after publication replays the same
job without a second cross-store commit. Lock ordering is always draft then job;
the request store never acquires a draft lock.

Email provenance uses its own source/account/message identity. No email pretends
to be manual input or a website SharePoint item. The existing source-history JSON
contract carries original Event identity/hash, assessment version, draft revision,
reported fact quotes, operator answers and explicit defaults. No tables or SQLite
schema versions change. Existing website import validation remains strict. Export
uses `EDN OS Email`, the source timestamp and the normal stable submission key;
email message identifiers are never SharePoint target item identifiers. If an
email and an existing website item are linked, the website target takes precedence
and the group cannot produce another create proposal.

Required canonical fields retain existing validation. Missing data stays in the
durable partial-draft queue and job creation refuses without fabricating contact,
site or scope. Service defaults to `Other / not sure` and urgency to `Routine`,
explicitly recorded as defaults, not extracted facts. Requested dates must satisfy
the existing ISO-date contract. Duration, access, equipment and explicit time remain
in source evidence for scheduling/review. No inferred schedule is approved here.

Exact source replay is idempotent. Changed answers create a pending source revision,
retain local corrections and invalidate prior approval through the existing audited
source-change path. Explicit source resolution is required before re-approval or
delivery. Matching forwarded copies use the existing potential-duplicate review
gate; an operator-confirmed same-work alias cannot independently approve/export.
General thread/forward reconciliation is not implemented by this bounded change.

Source attachment metadata causes promotion to refuse. Protected attachment-byte
promotion and association remain a separate prerequisite; evidence is never silently
dropped. Live sources, non-job correspondence, stale assessments and stale displayed
draft revisions cannot create jobs. No live connector, provider, calendar or
SharePoint transport is invoked.

Storage remains Linux/WSL private storage with native Windows refusal. New code can
read existing schema-3 stores. Older code refuses email provenance rather than
misclassifying it; retain stores and use the reviewed reader on rollback. No real
store migration or downgrade is authorised.

This PR is a callable workflow prerequisite, not full mobile email-to-job acceptance.
UI promotion controls, protected email attachment promotion, verified record reuse,
update/cancellation matching and reservation invalidation remain required. Full
hosted validation and independent exact-head Grok QA and Dot acceptance gate any
development integration. PR #53 stays unchanged for its pending review.
