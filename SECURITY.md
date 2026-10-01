# Security and sprint authority

Read the [platform security specification](docs/SECURITY.md), [Constitution](docs/CONSTITUTION.md), [context security](docs/intelligence-core/CONTEXT-SECURITY-MODEL.md) and [permission authority model](docs/intelligence-core/PERMISSION-AUTHORITY-MODEL.md). This onboarding summary does not weaken those rules.

## October development boundary

Dot and Grok may understand code and implement assigned repository issues in isolated development checkouts with synthetic fixtures. This task grants neither agent live production access nor Global Admin. Existing historical grants, credentials or app manifests do not establish present authority. No production systems, credentials, permissions or external services were changed here.

Keep secrets, real settings, tokens, PSTs, attachments, SQLite files, runtime logs, import reports and customer/source data outside Git and outside agent onboarding prompts. Use an owner-approved encrypted runtime root for real data. A drive letter or successful path validation does not verify encryption. Temporary test paths are for synthetic records only. The public GitHub repository must contain only publishable code, synthetic examples and non-sensitive documentation; classification review precedes issue/PR attachment uploads.

NV1 or Defence-related handling is not validated by this audit. Do not assume an engineer's clearance, an AI subscription or an existing Microsoft login permits classified, Defence, former-employer or customer content to be disclosed to either provider. Elliot must establish handling requirements and authorized environments before such data is accessed. No classified data is needed for the sprint.

## Controls to preserve

- Source archives and Microsoft reads remain read-only by default; website writes are a separate service boundary. Operations importer writes only its selected local derived DB, not Outlook.
- Memory content cannot be uploaded to cloud AI. The PA-009 provider code has independent disclosure, approval, preflight, budget, retry, freshness and result-retention controls. Its existence authorizes no dispatch and does not authorize Grok disclosure.
- Intelligence checks tenant/principal/purpose/domain/classification and source scope before retrieval. Private/global and personal/business evidence remain separated.
- Events retain immutable source content and `(source, source_account, external_id)` provenance. AI outputs and manual triage must remain derived state.
- Internal proposal approval is not execution authority. No sending mail, external write-back, unattended action execution or production deployment is included.
- Protected stores use POSIX ownership/mode/locking safeguards. Windows failures must not be repaired by silently disabling protection. Support must be proven with an equivalent platform control or an explicit unsupported-platform error.
- No sensitive source bodies, credentials or raw provider payloads in logs, PR descriptions, CI artifacts or debugging transcripts.

## Owner decision triggers

Stop dependent work and escalate to Elliot for new source access, data-root/ACL changes, credentials, tenant permissions/consent, cloud disclosure, architecture outside scope, budgets, production release, migration/deletion, merge authority or classification uncertainty. Provide the exact proposed change, reason, evidence, bounded scope, acceptance check and rollback. Continue independent synthetic tasks while awaiting the decision.

Expired Work Capture/PA-005/PA-009/delegation records are never reusable approval. Any fresh live-read acceptance requires its own exact scope and current owner authority; do not bundle consent expansion into a coding ticket. Do not create or activate an EDN delegated grant for this sprint merely because the feature exists.

If sensitive material is discovered accidentally, stop copying it, avoid printing it, inform Elliot with metadata only and arrange owner-led containment. Do not rotate credentials or alter access as an unsolicited fix.
