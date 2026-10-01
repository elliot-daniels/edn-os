# EDN OS autonomous build — executive briefing reliability

## Starting state

Inspected on 2026-09-15. Four pre-existing worktrees share the EDN OS Git repository. All were clean; no branches were merged.

| Worktree suffix | Branch / state | HEAD |
|---|---|---|
| `2026-08-28/.../work/edn-os` | feature/uwc-state-reconciliation | a19e85830846f0754e57a67455c7a1ae7434304c |
| `2026-08-28/.../work/edn-os-ci-validation` | chore/uwc-linux-validation | 3faa51cb0367acb824437f763c7701501354a7f5 |
| `2026-08-29/.../work/edn-os-approved` | detached | 9f87f4295138a013271720c115d809bb924356f7 |
| `2026-09-01/.../work/edn-os-uwc-solution-scaffold` | feature/uwc-solution-scaffold | f45e2b3b59d87ac1928048cda5093bd6916a6ba2 |

GitHub confirms the first two branch heads and the approved commit on `feature/universal-work-capture-v0.1`. The intelligence branch is `560421510d70b2a6ee3480f99321b2e163d5b706`; its intelligence implementation is already present in a19e858. Comparing its source/tests to a19e858 shows only UWC additions. The approved worktree has the same source/tests as a19e858. Main remains `5414dc10d6e92d36fa5c52811875cead5898d30e`.

UWC has a known diagnostic commit mismatch: local f45e2b3 and remote 839e75ca38138bfb079a1f81f41d69c63215ee56 have identical trees but different commit metadata. It was left untouched. No uncommitted work was swept into this feature.

New isolated worktree: `2026-09-14/files-pasted-by-the-user-edn/work/edn-os-executive`, branch `feature/executive-brief-reliability`, based on a19e858.

## What the implementation genuinely supports

- Memory: canonical email records, SQLite/FTS5, resumable/batched ingestion and CLI, directory imports, PST extractor proof-of-concept. This inspection did not import business data or verify production ingestion health.
- Retrieval/knowledge: keyword candidate retrieval, deterministic reranking, grounded extractive answering, rule-based entity/relationship extraction, persisted knowledge graph and provenance. This is not a verified production semantic/vector search deployment.
- Connectors/Core: capability manifests, registry health/authentication state, purpose/domain/classification policy, explicit scope, conformance tests, local document discovery/catalogue/search, bounded Outlook and Calendar read paths. SharePoint Business OS is a synthetic-tested read connector; this session did not activate it against operational lists.
- Intelligence: multi-source context assembly, typed fact/inference/recommendation distinctions, deterministic daily briefing, sessions, internal action proposals/review, local scheduler/run lifecycle, backup/status. The local UI currently wires email, optional knowledge graph, and an explicit unavailable Calendar capability; implemented connectors are not all enabled merely because code exists.
- Optional OpenAI: projection/disclosure boundary, validation, approval-bound dispatch, audit/preflight/budget/result stores and temporal checks. No provider call was made. Protected stores contain POSIX-specific ownership/permission/locking checks that do not currently pass Windows tests.
- Development/jobs: durable delegated-development authority/audit/orchestration and local job queue/worker. These are not a customer job-request workflow.
- Work/IMS: synthetic UWC logic, SharePoint contract/schema scripts and ALM artifacts. Live app-to-flow binding remains blocked separately.
- No implemented end-to-end quote/proposal sales pipeline, website job-request ingestion, asset management or production executive assistant was established by source inspection. Internal action proposals are not customer quotes.

## Gaps ranked and workstream selected

1. Reliable daily briefing over available evidence: immediately useful, builds on existing policy/retrieval and is independent of UWC. Selected.
2. Protected-store Windows support or a verified supported Linux execution environment: major reliability/deployment foundation; do not remove security checks to hide failures.
3. Approved operational Projects/Clients/Actions read integration: high business value, but synthetic connector tests do not prove live authorization/mapping.
4. Ingestion freshness, coverage and performance diagnostics across email/documents: prevent stale or missing source material from looking authoritative.
5. Complete local scheduler/application wiring with an owner-reviewed source configuration; then evaluate quotations and other consequential workflows.

Three concrete defects drove implementation: an individual connector outage aborted the entire brief; event age was confused with whether a meeting had ended; and the daily-brief request was used as an FTS keyword question, missing recent email whose text did not match the generic prompt.

## Implementation completed

`intelligence/context.py`, `models.py`, `service.py`, `__init__.py`:

- Preserve permission evaluation before retrieval. Known connector failures become content-free gaps; healthy sources still contribute. No automatic retry, consent, scope expansion, credential refresh or outbound action.
- Add optional, backwards-compatible source coverage to assembled context and responses: retrieved/empty/unavailable/partial; returned/admitted/selected counts and bounded reason codes. These describe only the retrieval attempt, not the entire source's completeness.
- Enforce context limits at use time, reject misattributed/out-of-domain/non-finite evidence, deduplicate exact IDs before selection, reject conflicting IDs instead of overwriting citations, and balance by capability rather than a source-supplied display label.
- Keep unexpected programming errors visible to the existing failure lifecycle.

`intelligence/brief.py`:

- Render partial/empty/unavailable retrieval as explicit coverage gaps, including when a source contributed some valid evidence.
- Reuse existing temporal rules for calendar boundaries. Ended events and events with missing boundaries cannot become upcoming priorities or immediate actions. Misdated future non-calendar records cannot establish current state.

`memory/storage.py`, `retrieval/keyword.py`, `retrieval/engine.py`, `intelligence/adapters.py`, `service.py`:

- Add bounded recent-email retrieval to the existing store/engine. Daily brief selects the previous seven days through the supplied reference time, ordered by sent instant then exact source key; ordinary question search remains keyword-based.
- Reuse canonical records, excerpts and provenance. No new database, index, connector, provider or external system was introduced.
- Exclude unknown, timezone-naive and future sent times from recent activity. Compare UTC offsets as instants; inclusive start/end boundaries are tested.
- Convert expected local retrieval failures to safe coverage gaps.

`retrieval/reranker.py`, `intelligence/adapters.py`:

- Legacy naive timestamps no longer crash mixed-timezone keyword results. They receive no recency bonus and appear with unknown freshness; no timezone is invented.

Added 33 behavior tests in `tests/intelligence/test_brief_reliability.py` and `test_recent_email_brief.py`.

## Validation

Full Windows baseline: **457 passed, 92 failed, 1 skipped** (550 collected).

Full Windows final: **490 passed, 92 failed, 1 skipped** (583 collected). Exact failure-node comparison finds **zero new failures and zero removed baseline failures**. The same 92 pre-existing failures remain: 90 AttributeErrors, one OSError and one filesystem-root assertion, concentrated in POSIX-only protected-store/delegation behavior and a platform-dependent root test. The full suite is not claimed green.

Ruff on all `src` and `tests`: pass. Strict mypy with the project's Linux target: **118 source files pass**. This is static validation, not Linux runtime execution; WSL is not installed. Git diff whitespace check passes. Recent retrieval was tested on a read-only SQLite handle with unchanged database bytes. All added data is synthetic.

## Architecture decisions and limitations

Use the existing capability/policy/record/retrieval/brief abstractions. Additional fields have defaults. The recent mode changes evidence selection, not permission scope. Existing source adapters still use their configured windows/queries; this does not claim a comprehensive cross-source operational snapshot.

Recent email reads compare sent times in SQLite and limit returned rows, but an older database without a suitable expression index may require a timestamp scan. Benchmark on a representative authorized local copy before scheduling against a large archive. No production schema migration was performed. Local email freshness reflects the imported corpus, not live inbox synchronization.

Coverage cannot recover exclusions hidden inside an adapter; pre-filter source coverage remains a connector-contract follow-up. A source returning exactly its limit is conservatively marked potentially incomplete. Duplicate adapter capability IDs are rejected because the current composition contract has no per-instance identity; multi-list composition should gain explicit identities rather than ambiguous citation overwrites.

## UWC and owner decisions

UWC is parked. No Microsoft resources were opened or mutated during this build session. Last separately recorded safety check: flow Off/zero runs, Work Log count 0, Project 4 Modified 2026-09-08T07:06:00Z. Binding session 95f7562b-5dd1-4436-9746-ab4e5bf4e43b remains for Microsoft support. No Gate B, activation, receipt-path live edit or default-environment change.

No owner approval is needed to review or continue repository-only work. Before live integration, obtain approval for exact tenant/site/list/mailbox/calendar IDs, read-only fields/windows, permitted local storage, execution schedule and principal. Do not request broader consent by default. Scheduling, cloud provider disclosure, customer writes, sending messages, deployment and UWC execution are not authorized by this feature.

## Five next steps

1. Validate the full suite on supported Linux and implement a reviewed Windows protected-store boundary if Windows is the chosen runtime; preserve fail-closed ownership/ACL/locking guarantees.
2. Wire the existing daily scheduler to a reviewed local-only source configuration and verify a synthetic scheduled run/restart end to end; do not enable live schedules implicitly.
3. Extend connector results with source-instance identity and pre-filter/truncation/freshness coverage, then admit exact approved Projects/Clients/Actions projections.
4. Benchmark and index recent-email time-window queries on an authorized copy; add ingestion-lag reporting and bounded recent-document selection.
5. Build project/action intelligence on those verified projections, with deterministic deadlines and provenance; keep customer proposals and external execution behind explicit review.
