# Synthetic automated intake

This additive workflow reads caller-supplied synthetic fixture mappings only. No
website/SharePoint HTTP client, source credentials, scheduling or live data access
exists. The exact website contract1.0 source is commit
f2f91d415e57d8ec017bf6ddad481d30c2a3c50d, as documented in
WORK-INTAKE-CONTRACT.md. All ten form fields plus source, submittedAt and
contractVersion are required; extra fields fail closed. Source must be
EDN Systems Website, submittedAt an aware UTC timestamp, and the encoded fixture
is bounded to32KiB. Existing form validation/normalization applies.

The caller supplies a bounded opaque synthetic external ID. Registry insertion,
draft request and first revision commit together. Concurrent replay retains the
same UUID and first original contract and returns the existing current local
revision, preserving any later human edits/approval. It never auto-approves.
Original source/time remain separate provenance; dry-run export of approved local
revision uses that source/time and explicitly labels synthetic_import. It does not
claim remote synchronization, mint EDN-JR IDs or transmit attachments.

Explicit initialization upgrades only a compatible local intake version1 store
to version2 by transactionally adding the registry. Read-only version1 use remains
supported, while import requires explicit upgrade. Existing request and revision
rows remain untouched; a failed upgrade rolls back. Older version1 code rejects
version2 rather than silently interpreting imported provenance as manual. Rollback
disables the import UI and retains its local database; no automatic downgrade or
source-row rewrite is performed. This depends on the core Work Intake PR and must
be reviewed as a stacked change, with full hosted CI and exact-head independent QA.
