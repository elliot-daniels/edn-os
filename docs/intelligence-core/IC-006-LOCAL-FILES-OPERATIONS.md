# IC-006 Local Files Operations

## Outcome

IC-006 operationalises metadata-only Local Files discovery without expanding ingestion authority. It adds a durable traversal cursor, strict external JSON loading, a small Core-routed CLI, deterministic capability-opportunity summaries and a separate single-GO live-discovery pack.

## Durable traversal

Discovery is deterministic depth-first traversal ordered by configured root ID and directory-entry name. A checkpoint token remains in the generic IC-003 `Checkpoint`; the protected Local Files catalogue stores the token's versioned cursor JSON. The cursor contains:

- cursor schema version;
- ordered root IDs and current root index;
- the active directory stack only;
- each frame's root-relative directory, next entry offset, device, inode and nanosecond modification time; and
- existing connector version/configuration hash binding in the cursor row and generic checkpoint.

A new connector/worker process loads the cursor from SQLite and reopens only active stack directories. Completed subtrees and file candidates before the checkpoint are not restated or reprocessed. Directory identity or modification drift on the active stack fails as incompatible source state. Candidate writes remain duplicate-safe through the catalogue's stable resource primary key and upsert transaction.

Memory is bounded by one sorted directory listing plus the current candidate batch and depth-sized cursor stack. This is intentionally a local persistent-job cursor, not a distributed crawler.

## Configuration

`load_config()` accepts schema `1.0.0` JSON and rejects unknown fields/types, relative roots/storage/exclusions, filesystem-root scope, overlapping roots, storage within approved roots, storage within a detected repository unless the development override is explicitly supplied, ambiguous extension rules, unsafe within-root symlink mode without same-filesystem enforcement, non-metadata discovery and invalid Core domain/classification envelopes.

The safe example at `examples/local-files-config.example.json` contains synthetic paths and identities only. Operational configuration and authority files must remain protected and outside Git.

## CLI and authority route

The module entry point is `python -m edn.connectors.local_files.cli`. It supports:

- `validate-config`: strict validation and configuration hash;
- `capabilities`: configuration-specific connector manifests;
- `discover-plan`: resolved read-only mode, exact root/configuration and current policy decision;
- `discover`: create or resume a persistent metadata-only discovery job, optionally running one worker batch with `--run-next`; and
- `summary`: deterministic catalogue summary and capability opportunities.

`discover` requires a protected authority JSON containing a serialized `PrincipalContext`, `Purpose` and `PolicySet`. The CLI evaluates the Capability Registry and Permission Evaluator before it creates a job. Execution then goes through `JobService`, `JobStore` and `LocalJobWorker`, which reauthorizes current capability, policy, tenant/domain, classification, scope, connector version and configuration hash. There is no CLI ingestion command.

## Summary model

Summaries include file and byte totals, root/excluded/warning counts, category and extension counts, deterministic age buckets, already-known, currently ingestible and unsupported counts. Unsupported groups become `capability_opportunities` with category, file count, bytes and missing capability. This is adapter-gap evidence, not semantic relevance or business value.

## Synthetic benchmark

Run on 10 August 2026 in the repository WSL environment using 100 directories containing 100 empty `.txt` files each:

| Mode | Calls | Time | Throughput | Peak Python allocation |
|---|---:|---:|---:|---:|
| Cold, one batch | 1 | 50.148 s | 199.4 files/s | 17.80 MiB |
| Durable resume, 1,000-file batches | 11 | 42.917 s | 233.0 files/s | 2.18 MiB |

The resumed catalogue contained 10,000 unique candidates and zero duplicates. Cursor JSON averaged 176.1 bytes and peaked at 177 bytes for this shallow tree. IC-005's previous 1,000-file resumed run exceeded 124 seconds because every batch replayed the preceding tree; IC-006 completed the comparable run in 42.917 seconds. Filesystem cache and host load affect absolute throughput, so the material result is bounded completed resume and the absence of candidate replay.

## Limitations

- Each active directory is sorted in memory; a single directory with millions of entries could still be costly.
- Active-stack directory modification invalidates the checkpoint and requires a fresh discovery instead of attempting ambiguous reconciliation.
- Age buckets use the catalogue host's current time.
- Metadata discovery does not infer semantics, parse documents, hash content or ingest automatically.
- Live scope, protected paths, classification, authority, execution window and retention remain owner decisions in the approval pack.
