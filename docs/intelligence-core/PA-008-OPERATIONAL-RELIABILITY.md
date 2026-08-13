# PA-008 - Daily Intelligence Operational Reliability

## Scope and non-activation

PA-008 adds a local scheduling/orchestration abstraction, durable Daily
Intelligence run history, structured status, and an allowlisted operational
backup/restore contract. It does not install cron, systemd, Windows Task
Scheduler, a cloud scheduler, a background service, automatic morning delivery,
notifications, live-source access, or external execution. A future activation
increment must choose and owner-approve any production deployment mechanism.

## Scheduling model

`DailySchedule` has an identity, daily cadence, local run time, timezone, next
expected run, last attempted run, and last successful run. The timezone is fixed
to `Australia/Adelaide`; all persisted and compared timestamps are timezone-aware.
The next occurrence is constructed from an Adelaide local date and time, then
converted by `zoneinfo`, so daylight-saving offset changes do not turn the
schedule into naive arithmetic. The default local time is 08:00.

`DailyIntelligenceScheduler` only decides whether the bounded local workflow is
due. It does not create capability authority, alter a request context, invoke
connectors directly, or install a scheduler. The caller supplies the already
authorised Daily Intelligence runner.

## Run lifecycle and idempotency

Each logical run is identified deterministically from `schedule_id` and the
scheduled instant. States are `running`, `completed`,
`completed_with_gaps`, `failed`, and `missed`; `due` is the scheduling condition.
The durable run stores scheduled/started/completed timestamps, attempt number,
result reference, evidence-gap count, failure code/detail, retry safety, and
missed-run reason. It stores no transcript, secret, token, raw Graph payload, or
brief body.

Repeated scheduler calls for the same due instant cannot create another logical
run. Suppressed attempts are appended to the same content-free audit history,
including calls after a completed run while the next cadence is not due. A
failed run is not silently re-executed; only an explicit `retry()` call for a
run marked `retry_safe` creates the next attempt on that same logical run.

## Missed runs and failures

`mark_missed()` records one explicit `missed` run and advances only one cadence;
it does not construct an unbounded backlog. A scheduler-resume check before the
next cadence is due returns the recorded missed state. Failure uses deterministic
codes such as `authority_denied`, `brief_assembly_failed`, and
`scheduler_interrupted`. A failed attempt never becomes a successful briefing,
never advances `last_successful_run`, and never overwrites the previous result.

`completed_with_gaps` is a successful local run whose PA-007 result explicitly
contains evidence gaps. It is healthy-but-visible in status; missing evidence is
not converted to an empty or current claim.

## Observability

`DailyOperationsStore` is a separate small SQLite operational store with a
version marker, schedule row, run rows, and append-only content-free audit events
using the existing `edn.development.models.AuditEvent` contract. The structured
`DailyOperationalStatus` answers:

- health (`Healthy`, `Attention required`, or `Not yet run`);
- last successful run;
- latest attempt and its status/failure code;
- next expected run;
- whether recovery is required; and
- whether the local scheduler state is healthy.
- whether the next scheduled run is currently due.

`render()` provides a concise owner-facing local representation. It is not sent
or exposed remotely.

## Backup boundary

`OperationalBackup` copies only explicitly supplied operational files into a new
destination. The caller must name each component. A deterministic manifest
records backup ID, creation time, schema version, component names, filenames,
sizes, SHA-256 hashes, and excluded categories.

The intended backup set is local operational state such as the Daily Operations
SQLite store and separately approved local job/session/action stores. Repository
code and JSON configuration are reconstructable from Git. Secrets, credentials,
authentication tokens, raw Graph payloads, protected PA-005 evidence, unrelated
files, and source bodies are excluded and never copied casually. The manifest
contains metadata only, not component contents.

Verification fails closed on missing manifests, incompatible schema, missing
components, size mismatch, or hash mismatch. Restore requires a new, non-existing
isolated target and therefore cannot overwrite live operational state. Synthetic
tests restore into temporary directories only; no live or protected database is
opened, modified, or recovered.

## Validation and remaining owner boundary

Synthetic tests cover a due run through completion, repeated invocation, failure
and safe retry, missed-run handling, Adelaide DST transitions, status rendering,
backup integrity, corruption, incomplete backup, schema incompatibility,
prohibited material, and restore-overwrite refusal. Existing JobStore remains the
authoritative resumable/reauthorization mechanism for connector jobs; PA-008 does
not replace or broaden it.

The result is operationally ready for a later activation decision, not automatic
delivery. Production scheduler installation, unattended execution, external
delivery, new live-source access, model/provider disclosure, and any external
action remain owner-authority boundaries.
