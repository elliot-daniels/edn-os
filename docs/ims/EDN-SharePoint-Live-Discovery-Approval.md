# EDN SharePoint Live Discovery Approval

Status: Controlled discovery and offline assessment completed; implementation review required

Final window approved by Elliot Daniels in the originating IMS-003 Codex task:
7 August 2026, 5:00–5:30 PM Australia/Adelaide (ACST). The corrected exporter
used new no-clobber inventory and backup paths. Read-only discovery completed,
the ten-file inventory was hash-verified and backed up, and the refined offline
assessment completed in the separately approved report path.


This document is the human authorization gate for a future IMS-001 live,
read-only SharePoint metadata inventory. Completing this template does not execute
the discovery. Approval applies only to the exact values and window recorded
below; any change requires a new decision.

## Approval record

Approval recorded from the named owner in the IMS-003 Codex task. Identifiers
below were supplied or explicitly confirmed by the approver; none were inferred.

| Required field | Approved value |
|---|---|
| SharePoint site URL | `https://edn123.sharepoint.com/sites/EDNSystems` |
| Tenant identifier | `aae6ab79-45eb-4829-a04f-595becdb936d` |
| PnP/Entra application client ID | `d08166f6-2074-4590-8edf-bb8275e9eb11` |
| Delegated permissions | SharePoint `AllSites.Read` delegated permission |
| Operator identity | `elliot@ednsystems.com.au` |
| Execution date and window, including timezone | 7 August 2026, 3:00–4:00 PM Australia/Adelaide (ACST) |
| Output directory | `F:\EDN OS\Working\SharePoint Inventory\2026-08-07` |
| Information classification | EDN Confidential |
| Retention period and disposal trigger | 12 months; delete after IMS implementation decisions are approved, required audit/troubleshooting activities are complete, and the retention period has expired |
| Approved primary storage location | `F:\EDN OS\Working\SharePoint Inventory\2026-08-07` |
| Approved backup location | `F:\EDN OS\Backups\SharePoint Inventory\2026-08-07` |
| Confirmation: no live inventory will enter Git | Confirmed; inventory and generated gap assessment will never be committed to Git |
| Confirmation: operation is metadata-only and read-only | Confirmed; no SharePoint content, configuration, permissions, structures, automation, retention, or tenant configuration may be modified |
| Named approver | Elliot Daniels |
| Approval date | 7 August 2026, Australia/Adelaide (ACST) |
| Decision: Go / No-go / Conditional | **GO** |
| Conditions or limitations | Read-only execution; interactive MFA; approved delegated permission only; output outside Git; EDN Confidential; review before implementation; no provisioning, schema changes, or automation deployment |
| Related Approval record or evidence link | IMS-003 owner approval recorded in the originating Codex task on 7 August 2026 |

## Scope being approved

The approved operation may authenticate interactively and retrieve metadata only
from the exact site URL above using
`installer/Export-EDNSharePointInventory.ps1`. It may write only the ten JSON
files defined by schema version `1.0.0` into the approved output directory.

It does not authorize:

- SharePoint provisioning, updates, deletion, permission changes, or content
  access;
- document, attachment, page, list-item, email-body, or group-membership export;
- invocation of Power Automate, Power Apps, webhooks, or connectors;
- unattended authentication or application credentials;
- scanning other sites, site collections, tenants, Teams, OneDrive, or Exchange;
- storing the live inventory in the repository; or
- beginning IMS provisioning or asserting compliance or maturity.

## Execution preconditions

Every precondition must be evidenced before a Go decision:

1. The owner has reviewed the discovery specification and exact script revision.
2. All approval-record fields above are complete and internally consistent.
3. The site URL, tenant identifier, and client ID have been independently checked
   against approved Microsoft 365 administration records.
4. The delegated permissions are documented and no broader than approved.
5. The named operator is permitted to read the scoped site's architecture
   metadata and will authenticate interactively with MFA.
6. The output and backup locations exist outside Git, are access controlled, have
   sufficient capacity, and match the approved information classification.
7. Retention expiry, disposal responsibility, and backup handling are agreed.
8. The repository is on the reviewed commit and the exporter passes its offline
   syntax and Pester safety tests.
9. The output directory contains none of the inventory filenames; the exporter
   will not overwrite prior evidence.
10. The operator understands that permission failures and unavailable sections
    must remain visible and must not be interpreted as absence.
11. A post-run reviewer and secure transfer path for IMS-003 analysis are named.
12. The approval decision is recorded before authentication begins.

## Go/no-go checklist

| Check | Yes/No | Evidence or comment |
|---|---|---|
| Exact site boundary approved | Yes | Owner confirmed exact URL |
| Tenant and client ID verified, not inferred | Yes | Both identifiers supplied and corrected by owner |
| Delegated permissions approved as least privilege | Yes | SharePoint `AllSites.Read`; no elevation authorized |
| Operator and MFA method approved | Yes | `elliot@ednsystems.com.au`; interactive MFA only |
| Execution window approved | Yes | Replacement GO: 7 August 2026, 4:28:01–4:58:01 PM ACST; owner confirmed ready to authenticate |
| Output path outside repository confirmed | Yes | Approved `F:` working path; directory absent before run |
| Protected primary and backup storage confirmed | Yes | Approved `F:` primary and backup paths; classification applies to both |
| Classification and retention confirmed | Yes | EDN Confidential; 12 months and approved disposal trigger |
| Exporter commit and schema version recorded | Yes | Commit `4ae2b19`; schema `1.0.0`; SHA-256 `55c52b02306fc6e5a9031a7d006f7a02588a94a6b9379947b1a5a5d8ee02b96f` |
| Offline tests reviewed | Yes | Exporter Pester: 11 passed, 0 failed |
| Output collision check completed | Yes | All ten filenames absent before run |
| No-live-inventory-in-Git confirmation recorded | Yes | Owner confirmed; `.gitignore` protection and external path verified |
| Read-only and metadata-only scope understood | Yes | Owner confirmed detailed mutation exclusions |
| Post-run reviewer named | Yes | Elliot Daniels |
| Named approver recorded a Go decision | Yes | Elliot Daniels; GO on 7 August 2026 ACST |

Approved protected gap-assessment output:
`F:\EDN OS\Working\SharePoint Gap Assessment\2026-08-07`.

Post-run reviewer: Elliot Daniels. The backup carries the same EDN Confidential
classification, 12-month retention period, and disposal trigger as the primary.

Any blank field, No answer, scope mismatch, unexpected permission request, script
change, output collision, or inability to protect the inventory is a **No-go**.
Stop before authentication and return the decision to the owner.

## Execution and evidence record

Complete only after a separately approved run. Do not place tenant-sensitive
values in Git; reference their approved operational record instead.

| Field | Result/reference |
|---|---|
| Approval record reference | IMS-003 owner approval recorded in the originating Codex task on 7 August 2026 |
| Exporter commit and SHA-256 | Based on `4ae2b19` with reviewed compatibility fix; `7f4b4423c64fe5309de5d15f067f001e45ce6ae3f324e0e0e044a507b83c2f06` |
| Inventory schema/script versions | Schema `1.0.0`; script `1.0.0`; 10 expected files produced |
| Actual start/end time | Approximately 5:04:43–5:06:14 PM ACST on 7 August 2026 |
| Operator | `elliot@ednsystems.com.au`; interactive delegated MFA completed |
| Secure inventory location reference | `F:\EDN OS\Working\SharePoint Inventory\2026-08-07-rerun-1` |
| Backup confirmation reference | `F:\EDN OS\Backups\SharePoint Inventory\2026-08-07-rerun-1`; 10 files plus manifest, zero hash mismatches |
| Inventory file hash manifest reference | Backup `inventory-manifest.sha256`; manifest SHA-256 `9BB2FAE8BC8B6631171BF31D3A5849CE368E41FA0D0FA6F1F63F7C1A29D35220` |
| Warnings and unavailable sections reviewed | Content types, list/site permissions, Power Apps, Power Automate definitions, external connector configuration, and Purview policy bodies unavailable; treated as unknown |
| Deviations or incidents | Initial inventory was incomplete due unsupported PnP list include and was preserved/backed up. Corrected exporter passed 12 tests and completed. First comparator output over-reported field overlap and was preserved; refined comparator passed 12 tests and completed at `F:\EDN OS\Working\SharePoint Gap Assessment\2026-08-07-rerun-1`. No SharePoint mutation occurred. |
| Reviewer and review date | Elliot Daniels; decision review required before any implementation or provisioning |

## Decision authority

The named human approver remains authoritative. Automation may validate supplied
values and safeguards but cannot approve the run, broaden permissions, accept a
deviation, or authorize later SharePoint changes.
