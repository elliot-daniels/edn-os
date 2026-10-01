# IC-005 Local Files Discovery and Controlled Ingestion

## Architecture and threat model

Local Files is the first real IC-003 connector and vertical proof through Core security, capability registration, policy evaluation, IC-004 jobs/checkpoints, verification, and audit. It treats filesystem visibility as neither permission nor authority. Source files may contain personal, client, credential, executable, or otherwise restricted material; paths themselves may be sensitive.

```text
External tenant configuration
  -> approved roots and domain/classification
  -> metadata-only discovery job
  -> persistent candidate catalogue
  -> exact candidate selection and deterministic plan
  -> approval bound to plan/scope/configuration
  -> reauthorized ingestion job
  -> content-addressed text store + UniversalRecordRef/EvidenceRef
  -> verification and content-free audit
```

Production code contains no EDN path, drive letter, tenant ID, person, or fixed domain/classification vocabulary. Automated tests use temporary synthetic roots only.

## Capabilities

The configuration-specific manifest declares existing Core `CapabilityManifest` values:

| Capability | Operation | Permission | Risk |
|---|---|---|---|
| `local-files.discover` | discover | `filesystem.metadata.read` | read |
| `local-files.inspect` | inspect | `filesystem.metadata.read` | read |
| `local-files.plan` | plan | `filesystem.metadata.read` | draft |
| `local-files.ingest` | ingest | `filesystem.content.read` | ingest |
| `local-files.verify` | verify | `filesystem.content.read` | read |

Supported domains come from configured approved roots. `runtime_states()` supplies explicit registry snapshots; installed code does not imply readiness.

## Approved-root and path security

`LocalFilesConfig` contains approved roots, exclusions, type filters, size/depth limits, hidden-file policy, symlink policy, filesystem-boundary policy, catalogue/content-store locations, and batch sizes. Every root carries its own `SecurityDomain` and `Classification`.

Paths are resolved conservatively at the adapter boundary. Discovery and ingestion require the resolved candidate to remain beneath its configured root. Exclusions must themselves be under an approved root. `..` traversal and symlink escape are rejected. Directory symlinks are not followed; file symlinks are ignored by default and may be considered only under `within_root`, still after resolved containment checks. Device IDs prevent silent mount-boundary crossing when configured. Hidden paths, excluded trees/extensions, depth limits, and allowed extensions are filtered before candidate creation.

The connector never executes, renames, moves, deletes, writes, or changes permissions/timestamps on source files. Executables are metadata candidates only and signal `executable.prohibited`.

Windows paths and WSL paths remain distinct source identities. A tenant may configure `C:\...` when the connector runs natively on Windows or `/mnt/c/...` under WSL. The connector does not pretend that those strings are universally equivalent; migration/identity mapping belongs in host-specific configuration.

## Metadata-first discovery

Discovery uses directory enumeration and filesystem stat metadata only. It does not open or hash file contents. Each candidate records stable path-derived resource ID, normalized resolvable path, root, filename, original extension, deterministic category, MIME guess, size, modified/created time, hidden/symlink flags, domain/classification, explicit metadata fingerprint, ingestion support, missing capability, state, and bounded warnings.

Traversal is deterministic by root, directory, and filename. Each call emits one bounded batch and an IC-003 `Checkpoint` when more metadata remains. IC-004 persists that checkpoint and cumulative count, allowing a new worker/connector process to resume from the last lexical resource boundary. The implementation rescans metadata to reach the marker, trading some repeated stat work for a compact, content-free checkpoint and bounded batch memory.

Inaccessible directories are represented as bounded type-only warnings such as `inaccessible:PermissionError`; paths and source content are omitted from audit.

## Deterministic classification and signals

Extension tables classify document, spreadsheet, presentation, PDF, email archive, mailbox, text, structured data, database, image, video, audio, archive, source code, executable, or unknown. No LLM or semantic ranking is used.

Only UTF-8 `.txt`, `.md`, `.json`, and `.csv` files within the configured size ceiling are directly ingestible in v0.1. Other candidates remain catalogued with explicit missing-capability signals, for example:

- DOCX -> `document-docx.ingest`
- PST/OST -> `outlook-archive.ingest`
- PDF -> `document-pdf.ingest`
- images -> `image.ingest`
- executables -> `executable.prohibited`

Discovery summaries report roots, candidates, already-known state, ingestible/unsupported counts, warnings, category counts, and unsupported capability count/bytes. `estimated_relevance` is only `heuristic_supported` or `unknown`; it is not represented as intelligence or semantic value.

## Fingerprints

The tiered model labels fingerprint meaning explicitly:

1. Path metadata: path, size, and modified timestamp are the cheap source-state tuple.
2. Metadata SHA-256: a deterministic hash of normalized path, size, and nanosecond modified time; useful for change detection, not cryptographic content identity.
3. Content SHA-256: computed only for approved, bounded ingestion files and used for content addressing and source-version provenance.

Discovery never performs level 3. Large-file hashing is deferred; files over the ingestion ceiling signal unsupported/missing adapter rather than being read.

## Candidate catalogue

A dedicated schema-versioned SQLite database—not email memory or the job database—contains:

- `schema_metadata`
- `discovery_runs`
- `candidates`

Candidate rows retain run/resource/root identity, path metadata, domain/classification JSON, fingerprint, state, selection, missing capability, optional resulting record envelope, and content hash. No file content is stored. Bounded transactions and `busy_timeout` are used without changing SQLite journal mode.

## Inspection, planning, and approval

Inspection accepts one stable candidate ID and returns metadata observations only: category, fingerprint type/value, and ingestion support. It does not sample content in v0.1.

Planning requires exact candidate IDs. The deterministic `ConnectorPlan` binds the sorted scope, supported/unsupported counts, categories, expected reads, byte/item estimates, no source mutations, no irreversible effects, approval requirement, and Local Files configuration hash. Any candidate selection or configuration change changes the plan hash.

Ingestion jobs use IC-004 `ApprovalBinding`. Reauthorization verifies job scope equals plan scope, plan configuration hash equals job/worker configuration, approval matches plan ID/hash/scope and remains valid, and current capability/policy/domain authority remains usable. Approval for subset A therefore cannot ingest subset B.

## Controlled ingestion and content storage

Before every approved content read, the connector resolves containment again, stats the source, and recomputes its metadata fingerprint. Material drift marks `source_changed`, raises `incompatible_source_state`, and requires rediscovery/replanning. It never silently reads a changed file under old approval.

Approved text is decoded as UTF-8 and stored under `<content-root>/<hash-prefix>/<content-sha256>.txt`. The write uses an exclusive temporary file and atomic replace inside the configured content store. Existing content hashes are reused. Original binaries are not copied, and source files remain authoritative.

Each ingested candidate produces:

- `SourceRef` for its approved root;
- `UniversalRecordRef` with stable candidate ID, source URI, domain, classification, `file.text` type, and content hash/version; and
- `EvidenceRef` with bounded `full-text` locator and `local-files.text` transformation/version.

The extracted text is not embedded in those envelopes or in job/audit records.

## Checkpoint, resume, and verification

Discovery and ingestion both return bounded IC-003 results with cumulative counts and compatible checkpoints. Ingestion processes exact candidate IDs in stable order. Unsupported candidates are accounted for but not read. Checkpoints bind connector/version, configuration hash, operation, exact scope, marker, and last durable count.

Verification confirms the discovery run completed or reconciles every supported approved candidate with a stored `UniversalRecordRef`. Unsupported selections produce `verified_with_warnings`; missing records produce `failed`; missing run completion produces `indeterminate`. IC-004 never converts failed or indeterminate verification into success.

Audit events retain job IDs, counts, reason/status, and stable candidate references where needed—not extracted text or file paths. Candidate paths remain only in the protected catalogue.

## Source evolution

Alpha behavior is conservative:

- modified after discovery: reject ingestion and require a new plan;
- renamed or moved: discover as a new path-derived resource, leaving prior provenance intact;
- deleted or inaccessible: retain catalogue/audit provenance and report inaccessible rather than deleting knowledge;
- duplicate copy: metadata candidate remains distinct by path; content SHA-256 later reveals identical content;
- deletion synchronization and tombstoning downstream knowledge are deferred.

## Synthetic proof and benchmark

The automated vertical test configures a temporary root, registers capabilities, executes persistent discovery, queries the catalogue, creates an exact plan, observes `approval_required`, binds approval, executes checkpointed ingestion, verifies, and queries Universal Record/Evidence references. Security tests cover traversal, symlink escape, excluded roots, domain isolation, scope/plan drift, post-approval source change, metadata-only discovery, source immutability, executable non-execution, checkpoint boundaries, content-free audit, and a second tenant.

On 10 August 2026 in the repository's WSL test environment, a generated temporary tree of 10,000 empty files completed a metadata-only single-batch discovery in 28.646 seconds: approximately 349 files/second with 17.10 MiB peak Python allocation measured by `tracemalloc`. No file content was opened. A 1,000-item resumable-batch run exceeded the two-minute benchmark limit because each compact lexical checkpoint currently restarts traversal from the root. This is safe and bounded but too expensive for deep repeated batches; a persistent directory-stack cursor is the highest-priority performance improvement before broad live discovery. Throughput will also vary significantly on Windows-mounted filesystems.

## Proposed first live discovery procedure — not executed

No production CLI or live configuration is created in IC-005. Before any real scan, create a protected tenant configuration outside Git containing only one narrow root, its explicit domain/classification, protected catalogue/content paths, exclusions, and metadata-only settings. Review the computed configuration hash and policy decision, create a discovery-only job, and obtain a separate explicit GO.

Proposed future command after a minimal CLI is approved and implemented:

```text
python -m edn.connectors.local_files.cli discover \
  --config /protected/edn/local-files-discovery-v1.json \
  --root-id approved-documents \
  --metadata-only \
  --run-next
```

Proposed configuration shape, with placeholders rather than real paths:

```json
{
  "roots": [{
    "root_id": "approved-documents",
    "path": "<EXPLICIT_APPROVED_ABSOLUTE_PATH>",
    "security_domain": "<EXPLICIT_DOMAIN_ID>",
    "classification_scheme": "<SCHEME_ID>",
    "classification_level": "<LEVEL_ID>"
  }],
  "excluded_roots": ["<EXPLICIT_SUBDIRECTORY_EXCLUSIONS>"],
  "discover_hidden": false,
  "symlink_policy": "never",
  "stay_on_filesystem": true,
  "metadata_only_discovery": true,
  "catalogue_path": "<PROTECTED_CATALOGUE_PATH>",
  "content_store_path": "<PROTECTED_CONTENT_PATH_NOT_USED_BY_DISCOVERY>"
}
```

The command is a proposed interface only and does not exist yet. No real directory was scanned during IC-005.
