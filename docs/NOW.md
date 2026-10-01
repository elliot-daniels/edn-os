# EDN Operations v1

## Current objective
Build EDN Operations Inbox: one local view of incoming business activity.
Adapt the existing Python, SQLite, Streamlit and Microsoft Graph stack.

## Current state
- Baseline: clean `feature/executive-brief-reliability`, commit `2ed21c6`.
  Work continues on `feature/operations-v1`. Remote refs refreshed 2026-10-01;
  the baseline includes local commits beyond its remote branch.
- Email memory, provenance, tests and governed read-only connectors exist.
  Current Outlook connector is metadata-only, bounded to `/me` Inbox.
- Website intake belongs to the separate `edn-systems-website` repository.
  Its Graph provider creates SharePoint job requests; leave this flow intact.
- Clients/Projects exist in SharePoint contracts; no local operational business
  relationship catalogue exists. The jobs package is an internal worker queue.
- Power Apps Work Capture is a saved scaffold, not an operational intake path.
  Existing source governance, authority boundaries and audit remain unchanged.
- Operations v1 now has an isolated Event store, replay-safe bounded Outlook
  content ingestion and a read-only Streamlit Inbox independent of email memory.
  See `OPERATIONS-V1.md` for commands and limits. AI outputs remain optional/empty.
- Multiple business mailboxes are supported. Cross-tenant accounts need separate
  authenticated runs into the same database. Live local authentication, mail-read
  permissions and an approved database path remain unconfigured in this session.
- Synthetic acceptance tests pass. The Windows full-suite baseline has 92 failures
  in existing modules; keep these platform limitations separate from Operations.

## Next three tasks
1. Configure approved local storage and Microsoft mail-read authentication;
   verify a bounded import and replay for each selected business mailbox.
2. Add read-only SharePoint job-request-to-Event ingestion using the existing
   website contract, preserving its source ID and intake/write flow.
3. Add a small human triage action (mark needs action/resolved), preserving
   immutable source content and provenance with an acceptance test.

## DO NOT WORK ON
- Deeper knowledge graph, universal work capture or autonomous-agent expansion.
- Power Automate or Power Apps expansion; no Microsoft source mutations.
- Unrelated refactoring, replacement of email memory or website job intake.
- New CRM relationship catalogue, cloud AI triage or automatic external actions.

Implement one acceptance-test-sized task per small validated commit. Runtime
data and credentials stay outside Git under the approved encrypted data root.
AI fields are reserved, optional derived data; source content stays authoritative.
