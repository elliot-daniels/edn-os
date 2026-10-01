# First October development tickets

Draft repository tickets, not published GitHub issues. All use synthetic data unless separately gated. Elliot owns priority/merge decisions; Dot owns technical specification and independent review; Grok is the proposed implementer. Estimates are rough engineering effort, excluding owner decisions and live access. Exact base SHA is assigned after OCT-01. No ticket authorizes production or Microsoft changes.

## OCT-01 — Establish the shared integration baseline (1–2 days)

Problem: remote main is 157 commits behind local Operations; a new engineer cloning main misses the inspected system.
Scope: inspect branch graph and existing PR state, inventory five local schema commits and six Operations commits, select a reviewable integration sequence with Elliot. Package the exact approved base for both engineers.
Acceptance: documented base/target SHAs, independent clean checkout reproduces source inventory and baseline; every unmerged range has an owner/review plan; original work preserved; onboarding docs included in the selected line.
Exclusions: no bulk merge, main rewrite, production release or permissions changes. Dependencies: none. Dot leads, Grok reproduces; Elliot approves target/sequence. Rollback: abandon proposed branch without touching source branches.

## OCT-02 — Add reproducible synthetic Linux PR validation (1–2 days)

Scope: .github/workflows plus setup/verification docs; adapt existing isolated UWC workflow into checks for OCT-01's target. Include full pytest/JUnit, Ruff, strict mypy and relevant frozen-artifact integrity validation. Pin a declared Python version; record dependency versions.
Acceptance: successful run on candidate SHA without source credentials/data, failure demonstrated for a broken synthetic fixture/check, no live API calls; documented required-check names. PowerShell checks separately documented for IMS changes. Branch protection proposal is concrete but settings changes require separate Elliot authority.
Dependencies: OCT-01. Exclusions: test skips to hide protection failures, automatic deployment, live credentials. Rollback: revert workflow commit. Grok implements, Dot reviews.

## OCT-03 — Prepare Operations storage and bounded live-read acceptance pack (0.5–1 day)

Scope: docs/OPERATIONS-V1.md and synthetic CLI validation evidence; write a no-secret operator checklist for selecting approved encrypted local storage, mailbox/tenant identity and already-approved read scopes. Identify Operations ACL/encryption gaps without changing them.
Acceptance: exact proposed commands, bounds, GET-only source behavior, replay-zero-new-Events criterion, malformed/page-limit accounting, per-mailbox provenance and cross-tenant separation, metadata-only result template and rollback/local cleanup plan. Elliot decisions explicitly listed; no real import run under this ticket.
Dependencies: OCT-01; real execution additionally gated on Elliot's current path/identity/scope approval. Exclusions: permission grants, credentials, new source reads, production DB creation or ACL changes. Rollback: documentation only. Grok prepares, Dot reviews, Elliot controls live acceptance.

## OCT-04 — Map SharePoint job requests to Events using synthetic clients (1–2 days)

Scope: inspect the separate website's repository contract read-only; document field/native-ID mapping, then add a bounded read-only adapter under operations and tests. Preserve website intake writes and original request IDs.
Acceptance: mapping is tied to inspected website commit; fixtures cover required/missing fields, timestamps, malformed records, paging/unsafe continuation, failure accounting and replay; source/account/native ID uniqueness preserved; no write methods or source mutations. Optional business links stay opaque.
Dependencies: OCT-01, OCT-02 and website contract availability. Exclusions: live SharePoint calls, schema creation, website changes, CRM inference. Rollback: revert adapter; existing Events/Memory remain compatible. Grok implements, Dot reviews.

## OCT-05 — Persist human needs-action/resolved triage locally (1–2 days)

Scope: operations storage/models/CLI or UI with a minimal separately stored triage overlay; source snapshot remains immutable. Define schema upgrade and rollback before code.
Acceptance: triage survives restart, is shown/filterable in Inbox, source body/raw payload/provenance unchanged, Outlook replay never resets local triage, transitions apply only to selected Event, read-only mode still refuses writes, missing DB remains uncreated. Add meaningful Streamlit/storage tests.
Dependencies: OCT-01, OCT-02. Exclusions: Outlook flag updates, automatic AI triage, sending mail, relationship catalogue. Rollback: disable overlay UI and preserve source Events; documented schema compatibility. Grok implements, Dot reviews; Elliot approves any significant schema design outside existing scope.

## OCT-06 — Show bounded import completeness and last-run evidence (1–2 days)

Scope: metadata-only local import run outcome and Inbox display for configured Operations intake. Distinguish complete, partial, failed and never-run without claiming whole-mailbox coverage.
Acceptance: page exhaustion/malformed/network interruption visible, source account/window/counts captured without bodies/secrets, replay remains safe after interruption, process restart retains last result, no scheduled imports, no completeness inference from merely having Events. Test successful/partial/failing cases.
Dependencies: OCT-02; coordinate storage edits with OCT-05. Exclusions: delta sync, background scheduler, live reads. Rollback: remove status display while retaining source store. Grok implements, Dot reviews.

## OCT-07 — Demonstrate Operations backup/restore with synthetic data (1 day)

Scope: local Operations recovery runbook and only necessary helper code; use SQLite-consistent backup handling rather than copying an active DB blindly.
Acceptance: restore synthetic Events/triage/status into a separate empty path, verify identities/counts/provenance/replay and read-only opening; interrupted backup does not replace a valid backup; no production paths touched. Document owner-approved real backup handling and limitations separately.
Dependencies: OCT-05/OCT-06 if schema changes land first. Exclusions: real database backup, retention deletion, enterprise storage/ACL changes. Rollback: discard synthetic restored copy; original DB unaffected. Grok implements, Dot reviews.

## OCT-08 — Fail clearly on unsupported protected-store platforms (1–2 days)

Problem: 91 of the 92 baseline Windows failures are in protected governance/provider store suites; remaining root-path test is platform-specific. Verify grouped evidence before editing.
Scope: choose one protected-store family per PR. Provide an explicit unsupported-platform diagnostic or an equivalent proven OS protection approach, subject to Elliot's design decision. Keep the root-path test adjustment separate.
Acceptance: no bare AttributeError for selected path, no silent protection bypass; Linux ownership/mode/symlink/locking/replay tests remain green; Windows behavior intentionally tested; baseline failure identity changes explained rather than simply skipped. Subsequent families become separate tickets if needed.
Dependencies: OCT-02, owner decision on supported runtime. Exclusions: wholesale OS abstraction/refactor, chmod removal, permissive fallbacks or production ACL edits. Rollback: revert selected family change. Dot specifies, Grok implements, independent reviewer for any Dot-authored code.

## OCT-09 — Reconcile enduring architecture and documentation (1 day)

Scope: docs/ARCHITECTURE.md, module map, relevant module specifications and onboarding docs. Resolve Memory schema/layout, feature-composition rule, stable module naming and historical-versus-current status using code evidence.
Acceptance: every CURRENT_STATE discrepancy has resolved wording or explicit owner decision; implemented schema/paths are clear, planned features labeled; links valid; fresh engineer can locate setup/tests/data contracts without a chat; no code move/module renumbering. Security requirements remain explicit even where implementation gaps persist.
Dependencies: OCT-01; verify against final accepted October base. Exclusions: speculative implementation to make docs true, runtime activation. Rollback: revert docs commit. Grok drafts, Dot reviews, Elliot approves design-intent changes.
