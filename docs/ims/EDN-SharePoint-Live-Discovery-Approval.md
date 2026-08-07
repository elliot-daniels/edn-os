# EDN SharePoint Live Discovery Approval

Status: Approval template — not approved

This document is the human authorization gate for a future IMS-001 live,
read-only SharePoint metadata inventory. Completing this template does not execute
the discovery. Approval applies only to the exact values and window recorded
below; any change requires a new decision.

## Approval record

Do not guess or pre-populate live identifiers.

| Required field | Approved value |
|---|---|
| SharePoint site URL | |
| Tenant identifier | |
| PnP/Entra application client ID | |
| Delegated permissions | |
| Operator identity | |
| Execution date and window, including timezone | |
| Output directory | |
| Information classification | |
| Retention period and disposal trigger | |
| Approved primary storage location | |
| Approved backup location | |
| Confirmation: no live inventory will enter Git | |
| Confirmation: operation is metadata-only and read-only | |
| Named approver | |
| Approval date | |
| Decision: Go / No-go / Conditional | |
| Conditions or limitations | |
| Related Approval record or evidence link | |

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
| Exact site boundary approved | | |
| Tenant and client ID verified, not inferred | | |
| Delegated permissions approved as least privilege | | |
| Operator and MFA method approved | | |
| Execution window approved | | |
| Output path outside repository confirmed | | |
| Protected primary and backup storage confirmed | | |
| Classification and retention confirmed | | |
| Exporter commit and schema version recorded | | |
| Offline tests reviewed | | |
| Output collision check completed | | |
| No-live-inventory-in-Git confirmation recorded | | |
| Read-only and metadata-only scope understood | | |
| Post-run reviewer named | | |
| Named approver recorded a Go decision | | |

Any blank field, No answer, scope mismatch, unexpected permission request, script
change, output collision, or inability to protect the inventory is a **No-go**.
Stop before authentication and return the decision to the owner.

## Execution and evidence record

Complete only after a separately approved run. Do not place tenant-sensitive
values in Git; reference their approved operational record instead.

| Field | Result/reference |
|---|---|
| Approval record reference | |
| Exporter commit and SHA-256 | |
| Inventory schema/script versions | |
| Actual start/end time | |
| Operator | |
| Secure inventory location reference | |
| Backup confirmation reference | |
| Inventory file hash manifest reference | |
| Warnings and unavailable sections reviewed | |
| Deviations or incidents | |
| Reviewer and review date | |

## Decision authority

The named human approver remains authoritative. Automation may validate supplied
values and safeguards but cannot approve the run, broaden permissions, accept a
deviation, or authorize later SharePoint changes.
