# EDN OS local morning loop — 2026-09-16

The repository now supports a locally invoked scheduled briefing through the
existing capability registry, policy evaluator, context assembler, intelligence
service and daily run lifecycle. Live Microsoft sources and persistent schedules
remain disabled. The demonstration is synthetic, not proof of live readiness.

Starting branch: `feature/executive-brief-reliability`.
Starting commit: `d34d1d9d705c54bf67a6cc409d64fa815a048a3e`, clean and synchronized
with the remote when this work began. Changes remain on that feature branch.
The final publication SHA is recorded in the session's publication receipt; a
commit cannot embed its own SHA in its content.

## Implemented capability

- `MorningBriefApplication` accepts explicit source adapters, limits, timezone,
  principal, registry and policy. It invokes the existing service and scheduler,
  atomically saves a content-hashed local JSON brief with provenance and
  coverage, and returns the artifact reference through the existing run model.
  It installs no background service, OS task or recurring schedule.
- Scheduler initial claims are insert-only, concurrent retries use compare and
  swap, and initialization cannot overwrite newer schedule state. A store is
  bound to one schedule. A restarted completed run is suppressed; an interrupted
  RUNNING attempt is visible and requires explicit recovery after its old worker
  is confirmed stopped. It never automatically steals a possibly active run.
  A saved completion can repair a not-yet-advanced schedule on the next tick.
  Timezone is configurable; the historical default remains Adelaide.
- Source batches retain source-instance identity, check time, pre-filter count,
  truncation/rejection reasons and freshness. Multiple list instances may share
  one capability. Context selection remains bounded and fair across instances;
  conflicting citation IDs are rejected, not overwritten.
- Local email reports recent evidence versus empty period, ingestion unknown,
  incomplete/failed import, stale import, recent snapshot and retrieval failure.
  **No import state claims that the live inbox was checked.** Import tracking
  uses existing email batch transactions; the unchanged one-connection-per-batch
  and progress-callback tests pass. No business mailbox was imported.
- The existing Streamlit runtime now uses this email coverage adapter and avoids
  making every fresh email an immediate priority. Its runtime builder was moved
  intact into an importable module so this wiring can be tested without executing
  the Streamlit page. Calendar remains authentication-required there.
- Calendar/Outlook morning adapters retain bounded connector diagnostics and
  instance-qualified evidence. Known HTTP/network/timeouts become typed source
  failures. Calendar rejects missing/malformed and ambiguous/nonexistent local
  boundaries, handles all-day/DST transitions, and treats an event ending at the
  reference instant as ended. No live credentials were acquired.
- Explicit SharePoint projections support projects, clients and actions using
  approved field mappings, canonical relationship IDs and timezone-aware dates.
  Deterministic rules identify overdue/due-today/next-seven-day deadlines, cite
  project/client context, and exclude closed items or actions on inactive
  projects. Unknown statuses, ambiguous relationships, unverified source state
  and invalid deadlines become gaps. No arbitrary recent record becomes urgent.

The `BusinessSourceAdapter` reuses the existing SharePoint connector. Its HTTP
client remains an injected protocol, not a newly activated production transport.
The exact live field mappings, choice values, relationship namespaces and query
contracts must be verified before operational reads. The activation proposal
records this limitation rather than inventing live schemas.

## Synthetic demonstration and local use

From the repository, with its development Python and `PYTHONPATH=src`:

```powershell
$env:PYTHONPATH = 'src'
python -m edn.intelligence.synthetic_morning tests/fixtures/morning/synthetic.json <new-local-state-directory>
```

This executes one due tick at the fixture's fixed reference instant. Repeating
the command with the same state directory suppresses the duplicate. It does not
wait for tomorrow or install any schedule. For a real host, construct
`MorningSourceConfiguration` with explicitly authorized injected adapters;
passing configuration does not authenticate or broaden policy.

The actual application/service/scheduler result was `completed_with_gaps` with
six source gaps. The fixture includes a recent email from a stale archive, an
ended meeting, an upcoming review, active/inactive projects, a client, overdue,
due-today/future/completed actions, and an unavailable notes source.

Result: **Review beam calculation** is overdue, **Confirm design assumptions**
is due today, **Atlas design review** is upcoming, and the project deadline is
identified. Client/project context has its own citations. Ended meetings,
completed actions and inactive-project work create no upcoming urgency. Healthy
evidence survives the unavailable source. The stale snapshot is disclosed.
Conflicting-evidence, crash/retry and concurrent-tick scenarios have separate
behavioural tests. No action proposal is dispatched or external call made.

The exact deterministic Markdown output is regression-tested in
`tests/fixtures/morning/expected.md`. All its content is explicitly synthetic.
Run artifacts contain only that synthetic fixture in this session.

## Validation and performance

- 39 new behavioural tests pass (morning application, connectors and storage).
- Full suite: **622 tests; 529 passed, 92 failed, 1 skipped**.
- Compared the complete failing test identities against the starting 583-test
  report: **all 92 identical; zero new failures, zero removed failures**. Existing
  tests were not weakened or edited to hide regressions. POSIX protected-store
  security remains unchanged and fail-closed on Windows.
- Ruff `src tests`: pass. Strict mypy, Linux platform target: **123 files pass**.
  This is static checking, not a claim of Linux runtime testing. Git whitespace
  validation passes. Full suite includes existing Intelligence/Core/Retrieval,
  connector, scheduler and database tests.
- Synthetic benchmark: 100,000 rows, 30 queries, last-seven-day window and ten
  results. Median **30.327 ms without index; 0.818 ms with index**, about **37x**.
  Maximums were 37.598 ms and 2.126 ms. Timings are machine-specific and warm
  local measurements, not a production SLA. No authorized business test copy
  was used and no business mailbox was opened for benchmarking.
- The expression index on `julianday(sent_at)` and the import-status table are
  additive, idempotent changes through `SQLiteEmailStore.initialise`, the
  existing schema initialization/upgrade mechanism. Read-only legacy retrieval
  performs no implicit migration; unchanged database bytes and explicit upgrade
  are tested. The benchmark is reproducible with
  `PYTHONPATH=src python tests/benchmarks/recent_email.py` and creates only a
  temporary synthetic database.

Machine-readable exact failure IDs, artifact hashes and benchmark measurements:
`docs/morning-brief-validation.json`.

## Limits and next decisions

1. Review `MORNING-BRIEF-ACTIVATION-PROPOSAL.md` for the smallest one-shot
   email/calendar pilot, preserving the existing PA-005 identity, EDN-category
   admission and consent boundary. It contains the exact proposed approval text.
2. Authorize only bounded SharePoint identity/schema/grant inspection if wanted;
   freeze actual internal field names, status vocabulary, relationship IDs and
   query semantics before considering operational-list reads. No live SharePoint
   transport or whole-list completeness is claimed here.
3. Confirm the business timezone (existing PA-005 Adelaide versus session Sydney),
   local storage protection/retention and desired schedule. No live schedule is
   enabled; any recurring activation requires separate owner authority.
4. Run the suite on supported Linux and resolve Windows protected-store support
   through an explicit security design before provider-backed/production use.

Bounds can omit records; pre-filter counts are counts fetched, not total mailbox
or list sizes. Query/cap/relationship gaps cannot be turned into claims that no
work exists. Model reasoning is neither required nor used. The new local output
store does not claim encryption or add a Windows ACL security model. A crash
between artifact save and run completion may leave an orphan local artifact;
explicit retry may create another, but cannot produce an external effect.

## Authority audit

UWC environment, application, flow, fixtures and separate worktree were untouched;
Gate B was not executed. No Microsoft operational read or mutation occurred. No
emails/messages, calendar edits, operational-list writes, finance/customer
actions, provider requests, consent changes, deployment, main merge or PR.
Only repository/local synthetic work and the authorized feature-branch code
publication were performed. Public Microsoft documentation was consulted for
the proposal; it is not evidence of current tenant permissions.
