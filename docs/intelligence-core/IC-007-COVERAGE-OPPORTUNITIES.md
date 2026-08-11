# IC-007 Representative Discovery and Coverage Opportunities

## Purpose

IC-007 improves metadata-only discovery reporting before any broader live scan. It does not add an ingestion adapter or infer file value. Operational roots, identities, authority records and protected paths remain external to Git.

## Coverage dimensions

Each deterministic group reports:

- record count and percentage of all discovered records;
- byte count and percentage of all discovered bytes;
- extension counts and extension diversity;
- 0–30 day, 31–365 day and over-365 day recency counts;
- `SUPPORTED NOW`, `MISSING INGESTION CAPABILITY`, `INTENTIONALLY PROHIBITED` or `UNKNOWN` status;
- current or missing capability;
- security domains and classifications represented;
- deterministic confidence; and
- explicit metadata-only and configured-scope limitations.

Coverage is not semantic value. A large file is not described as more important than a small file, and no file is opened to produce these measures.

## Bounded ranking

Only `MISSING INGESTION CAPABILITY` and `UNKNOWN` groups receive a coverage rank. Ranking is a stable lexicographic ordering by:

1. descending record count;
2. descending bytes;
3. descending extension diversity; and
4. category name as a stable tie-breaker.

There is no opaque weighted score. Supported and intentionally prohibited groups remain visible but unranked. Executables are never recommended for ingestion merely because they exist.

## Representative discovery controls

A representative plan must retain one exact approved root, one explicit domain/classification, metadata-only operation, hidden-path exclusion, disabled symlinks, same-filesystem enforcement, bounded batches, durable checkpoints and operational state outside Git. It must exclude obvious build/cache/dependency trees without silently excluding ordinary documents.

The approval record must bind configuration and authority hashes, scope, permission, execution window, exact command and recovery procedure. Plan preparation may initialise an empty catalogue schema; it must create no discovery run, candidates, job or content store. A separate GO is required before traversal.

## Scale and recovery

The file count is unknown until an authorised discovery because estimating it by traversal would itself perform the prohibited operation. Discovery remains bounded by configured batch size. The operator may stop between batches; the existing job ID and durable cursor resume the active directory stack without replaying completed candidates. Configuration or active-source drift fails closed.

Catalogue growth is observable through candidate totals, database size, checkpoint count and throughput. Content ingestion, hashing and semantic assessment remain separate later approvals.
