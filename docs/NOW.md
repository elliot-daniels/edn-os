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
- No Operations Event store or Inbox exists at baseline. Live mailbox identities
  and mail-read permissions must be configured before real ingestion.

## Next three tasks
1. Add a simple Event contract and isolated SQLite store with provenance,
   account-scoped duplicate protection and synthetic acceptance tests.
2. Ingest bounded Outlook business-mailbox reads using existing Graph/auth
   mechanisms; prove replay safety and source isolation with fake Graph tests.
3. Add a Streamlit Operations Inbox, newest first, needs-action/source/link
   filters and plain-text content; verify with synthetic UI tests.

## DO NOT WORK ON
- Deeper knowledge graph, universal work capture or autonomous-agent expansion.
- Power Automate or Power Apps expansion; no Microsoft source mutations.
- Unrelated refactoring, replacement of email memory or website job intake.
- New CRM relationship catalogue, cloud AI triage or automatic external actions.

Implement one acceptance-test-sized task per small validated commit. Runtime
data and credentials stay outside Git under the approved encrypted data root.
AI fields are reserved, optional derived data; source content stays authoritative.
