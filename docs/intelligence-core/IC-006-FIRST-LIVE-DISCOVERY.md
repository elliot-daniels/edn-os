# IC-006 First Controlled Local Files Discovery

## Status

Approval pack only. No real directory was scanned and no content was ingested while preparing IC-006.

## Proposed bounded operation

The first live run should scan one small, owner-selected business-document directory. Existing environment information identifies Windows Documents locations, but does not establish which single subdirectory is authoritative or its classification. The owner must therefore replace the protected configuration placeholders below; the repository example intentionally contains synthetic paths only.

| Control | Proposed value |
|---|---|
| Mode | READ-ONLY DISCOVERY |
| Roots | Exactly one |
| Root ID | `approved-documents` |
| Root path | Owner confirms one exact absolute WSL path |
| Security domain | Owner selects exactly `EDN` or `PERSONAL` |
| Classification | Owner confirms scheme, level, display name and rank |
| Hidden paths | Disabled |
| Symlinks | Disabled |
| Filesystem boundary | Stay on source filesystem |
| Content reads/hashes | Prohibited |
| Ingestion | Not available from the discovery CLI |
| Depth | 8, unless owner reduces it |
| Batch size | 250 candidates |
| Catalogue/jobs/content store | Exact protected absolute paths outside Git |
| Exclusions | Owner-confirmed cache, build, dependency and recycle-bin subtrees only |
| Output classification | Same as the selected root |
| Retention/disposal | Owner confirms before GO |

The content-store path is configuration-bound for later controlled ingestion but is not used by discovery.

## Pre-GO evidence

Before requesting GO, the operator provides one approval record containing:

1. configuration path and SHA-256;
2. computed configuration hash;
3. exact root ID and resolved root path;
4. security domain and classification;
5. catalogue and job database paths outside Git;
6. exclusions, depth, extension and size rules;
7. policy decision showing `local-files.discover` / `filesystem.metadata.read` is usable for the named principal and purpose;
8. `discover-plan` JSON confirming metadata-only operation and no content ingestion;
9. execution window, owner, retention, disposal, backup and post-run reviewer; and
10. exact command below with protected file paths substituted.

Any mismatch, missing authority, configuration change, expired window, broader root, repository storage, symlink relaxation or request to read content is a stop condition.

## Single-GO approval

The owner may approve the complete bounded operation with:

> GO — approve the IC-006 metadata-only discovery exactly as recorded in the attached pre-GO evidence, during the stated window. No content ingestion, scope expansion or filesystem mutation is authorised.

This GO applies to one configuration hash, one principal/purpose, one root ID and one execution window. It does not authorise ingestion or a second root.

## Proposed commands

Validate and review without scanning:

```text
python -m edn.connectors.local_files.cli validate-config --config <PROTECTED_CONFIG_JSON>
python -m edn.connectors.local_files.cli discover-plan --config <PROTECTED_CONFIG_JSON> --authority <PROTECTED_AUTHORITY_JSON> --root-id approved-documents
```

After the single GO only, create and execute one resumable metadata batch:

```text
python -m edn.connectors.local_files.cli discover --config <PROTECTED_CONFIG_JSON> --authority <PROTECTED_AUTHORITY_JSON> --root-id approved-documents --job-id <APPROVED_JOB_ID> --run-next
```

Repeat the same `discover ... --run-next` operation through the existing job runner for remaining checkpoints; do not create a different job ID. Review the resulting run ID with:

```text
python -m edn.connectors.local_files.cli summary --config <PROTECTED_CONFIG_JSON> --run-id <RUN_ID>
```

## Expected summary

The summary reports total files/bytes, category and extension counts, deterministic age buckets, already-known, currently ingestible, unsupported, excluded and warning counts. `capability_opportunities` groups unsupported file counts and bytes by required capability such as `document-docx.ingest`, `document-pdf.ingest`, `outlook-archive.ingest` or `image.ingest`. These are deterministic adapter opportunities, not claims about file value or meaning.

## Review and stop

After discovery, preserve the protected catalogue, jobs database, configuration, authority record, command output and configuration hashes according to the approved classification and retention. Review warnings and capability opportunities before proposing any ingestion. Stop; content ingestion requires a separate exact plan and approval.
