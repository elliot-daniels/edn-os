# OCT-07: explicit SQLite snapshots including committed WAL

Base: `21f49fbe90dc279bf1bd1accdf2cfee69618ae11` authoritative main.
Scope is the operational backup helper, focused synthetic tests and this document.
No Operations schema, import, UI, protected-store policy or live data is changed.

`BackupComponent(name, path)` remains ordinary-file mode. Recognized SQLite files
now fail closed before a backup destination is created: raw database copying can
omit committed WAL state. SQLite recovery requires explicit
`BackupComponent(name, path, sqlite_snapshot=True)`; the flag must be a real bool.
Explicit SQLite mode refuses non-SQLite files, and ordinary mode checks the header
again at copy time to refuse a database substituted after preflight.

SQLite mode reserves an exclusive component file, opens the source using URI
`mode=ro` and copies the main database through `sqlite3.Connection.backup`. It
never uses `immutable=1`, which could ignore active WAL. Existing link/reparse,
portable-name, prohibited-material and no-overwrite controls apply to both modes;
SQLite also checks source/target WAL, SHM and rollback-journal paths for links.
The new output alone is converted to DELETE journal mode and must pass
`PRAGMA quick_check(1)` before its bytes are hashed into the unchanged version-1
manifest. Restore copies that standalone snapshot into a new isolated directory.

Backup progress uses 128-page steps and a 30-second monotonic per-component
budget, including busy retries; retries sleep 50 ms with SQLite busy waits capped
at 100 ms. Output SQL uses a deadline progress handler. This bounds retry loops
and SQLite work at callback opportunities; it is not a hard deadline for an OS
filesystem call. A continuously changing/busy database may therefore fail safely
and need a separately approved retry. SQLite errors expose only a fixed safe
message. Interruption, corruption, timeout or output-integrity failure publishes
no completion manifest and never replaces an existing valid backup. Incomplete
new directories can remain for owner-directed cleanup; they are not restorable
completed backups.

Synthetic active-WAL tests keep a writer open, commit an Event and import outcome
without checkpointing the main file, and recover both in the new snapshot. Tests
verify manifest hashes, quick_check, Event ID/source/native provenance, durable
outcome, read-only opening, duplicate-safe replay, unchanged source/main WAL
bytes, existing-target refusal, ordinary-file compatibility, strict flags,
linked/reparse paths and sidecars, corrupt input, injected interruption and busy
retry deadlines. Existing backup security tests remain intact.

Read-only SQLite can use or create WAL/SHM coordination files; `mode=ro` denies
SQL writes to source content but is not a guarantee of zero filesystem metadata
or sidecar activity. No source checkpoint, journal-mode change or schema mutation
is requested. Callers still need owner-approved protected/encrypted local roots.
Path preflight and SQLite's subsequent path open retain the documented concurrent
parent-replacement/TOCTOU limitation; this change does not establish ACLs or a new
atomic-path guarantee. Each component is a separate main-database snapshot, not
an atomic cross-database set or a protected-store recovery policy.

Existing raw SQLite archives cannot be retrospectively certified WAL-complete by
a matching byte hash. This change authorizes no production archive inspection,
backup execution, retention deletion, ACL adjustment or deployment. Rollback is
to revert the helper/test/doc change; new snapshots retain the existing manifest
and restore format. Reverting restores the unsafe raw-copy behavior and must not
be presented as a production SQLite recovery method.

References: [Python SQLite backup API](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup),
[SQLite online backup](https://www.sqlite.org/backup.html), and
[SQLite WAL/read-only behavior](https://www.sqlite.org/wal.html).

The active-WAL fixture also keeps an uncommitted source update open during
snapshotting; recovery retains the committed Event and ignores that update.
Local focused validation: 68 passed across new SQLite and existing backup suites.
Initial full Windows candidate: 1288 passed, 92 known failures, 1 baseline skip;
strict baseline guard passed. Final exact-head evidence is recorded in the PR
handover after independent review. Linux-targeted mypy covers 137 source files;
it does not substitute for hosted Linux runtime checks.
