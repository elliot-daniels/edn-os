# Audited synthetic canonical updates

`EmailDraftStore.update_job` admits only a current synthetic job-update draft.
It holds draft then request locks, validates a complete bounded canonical snapshot
and alias audits, and requires one source-resolved non-terminal reference/customer/
site match. Matching and revision/hash recheck occur under the mutation lock.

Supported reported changes are contact name, email, phone, scope and ISO requested
date (mapped to preferredDate). Existing canonical validation applies. Other fields
are retained in the immutable email, but scheduling-only facts, equipment/access
or original attachments require review; they are not silently dropped or booked.
Customer/site/reference changes cannot be inferred into another job.

Each distinct accepted update records a new revision and normal local-operator
audit with source key/hash, actor/time and historical content hash, invalidating
approval. This is conservative even when a reported value equals current content.
Exact source replay validates that historical audit and returns current job state;
it never overwrites a subsequent correction, approval or cancellation. No new
schema/table, source mutation, transport or authority is introduced. Fields not
reported in the update and supporting attachments remain unchanged.

This is a bounded synthetic API prerequisite, not automatic mobile update handling
or calendar rescheduling. Reservation invalidation/cross-store coupling, original
email attachment promotion, forwarded/thread duplicate execution and general
unstructured extraction remain open. The source sender is unverified. Independent
exact-head Grok/Dot acceptance and full hosted CI are required before accepted
development integration. Main and the accepted b4a519b Android demo remain unchanged.

Linux/WSL local UI: private 0700 Linux parent outside Git, `umask 077`, existing dev
venv; `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`;
open `http://127.0.0.1:8502`. Subsequent restarts omit --initialise. Updates are
demonstrated through synthetic API tests, not a new mobile control. No live
Outlook/Calendar/SharePoint data or external AI processing is authorised.
