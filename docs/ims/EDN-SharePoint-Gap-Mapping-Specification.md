# EDN SharePoint Gap-Mapping Specification

Status: Implemented for synthetic/offline use; live inventory not supplied

## Purpose

This specification defines the deterministic, offline comparison performed after
a separately approved IMS-001 inventory. It prepares evidence for IMS-003 without
changing SharePoint, the inventory, Git, or operational systems. Recommendations
are design inputs for human review, not provisioning instructions.

## Inputs and trust boundary

`Compare-EDNSharePointInventory.ps1` accepts one explicit inventory directory
containing the ten JSON files defined by discovery schema `1.0.0`. It validates:

- required filenames, envelope shape, schema version, timestamp, and site URL;
- record arrays and stable IDs;
- cross-file list references;
- declared unavailable sections and discovery errors; and
- duplicate identities and secret-like properties.

By default an incomplete or malformed inventory is refused. `-AllowIncompleteInventory`
permits analysis only when incompleteness is represented in quality findings and
recommendations do not turn unavailable evidence into an absence claim.

The inventory is read-only. Reports go to a separate explicit directory outside
the repository, and existing report files are never overwritten.

## Comparison baseline

### Existing authoritative structures

- Projects
- Clients
- Actions
- Assets
- Approvals
- Executive Metrics
- System Status
- Work Log
- Quotes
- Engineering Knowledge

These remain authoritative where discovered. Matching does not prove that their
fields, permissions, automation, versioning, or retention are adequate.

### Proposed shared IMS structures

- Obligations and Requirements
- Processes and Controls
- Risks and Opportunities
- Assurance, Events and Findings
- Controlled Documents

These are architecture concepts, not assumed live objects. A missing exact name
may still be implemented by an existing differently named structure. A potential
`Create new` result is therefore low-confidence and always requires owner approval
after duplicate and semantic-overlap review.

## Classification model

Every relevant discovered list/library, plus each genuinely unmatched proposed
shared structure, receives one classification:

| Classification | Rule and meaning |
|---|---|
| `Reuse unchanged` | Exact authoritative-object match with no duplicate candidate or material control flag found in available metadata |
| `Extend existing` | Exact or strong field/name match where the object should remain authoritative but evidence indicates an IMS metadata/control extension may be needed |
| `Create new` | Proposed shared IMS structure has no exact, name-overlap, or field-overlap candidate in complete relevant discovery; low-confidence planning recommendation only |
| `Retire or consolidate` | Strong evidence identifies a duplicate object and a clearer authoritative object; never an automatic deletion instruction |
| `Needs owner decision` | Ambiguity, duplicates, unavailable evidence, sensitive permissions, automation dependency, or competing source-of-truth candidate prevents a safe conclusion |
| `Out of IMS scope` | No material match to existing authoritative or proposed shared IMS structures |

No recommendation authorizes creation, modification, migration, consolidation, or
retirement. `Retire or consolidate` always requires a human decision, dependency
review, retention review, and migration/rollback plan.

## Matching and evidence rules

Names are normalized to lowercase alphanumeric tokens with common separators and
plural variation removed. Exact normalized names are strongest. Token overlap is
supporting evidence only. Field overlap uses normalized internal field names and
excludes generic SharePoint fields such as ID, Title, Created, Modified, Author,
and Editor.

Duplicate candidates are produced when:

- two objects have the same normalized title or internal name;
- title-token similarity meets the documented threshold; or
- material non-generic field overlap meets the threshold.

The report must distinguish an exact duplicate candidate from a possible semantic
overlap. URLs, item counts, or similar field sets never justify deletion.

## Recommendation evidence

Each recommendation preserves:

- source inventory filename and deterministic record locator;
- list/library ID, title, internal name, type, and URL;
- relevant field and content-type IDs/names;
- permission inheritance and unique-permission indicators;
- versioning and retention indicators;
- views and automation references;
- architecture target and classification;
- rationale, risks, proposed owner role, confidence, and unresolved questions;
- discovery warnings, errors, and unavailable sections affecting the conclusion.

Evidence paths use JSON-pointer-like locations such as
`lists-and-libraries.json#/records/2`; they do not copy document or list-item
content.

## Control and quality flags

- Unique permissions are flagged for access review; inherited permissions are not
  automatically considered adequate.
- Missing versioning is a gap only when versioning metadata was available.
- Missing retention or sensitivity information is `unknown` when the relevant
  section was unavailable; it is never reported as no policy.
- Automation references create dependency risks and block automatic consolidation.
- Missing views are a usability observation, not evidence that the list is unused.
- Discovery errors, inconsistent site URLs, unknown schema versions, duplicate
  stable IDs, dangling list references, or missing required files reduce quality.

## Outputs

The explicit output directory contains deterministic UTF-8 reports:

```text
GapAssessment/
  gap-summary.json
  object-recommendations.json
  duplicate-candidates.json
  unresolved-decisions.json
  inventory-quality.json
  EDN-SharePoint-Gap-Assessment-Generated.md
```

JSON envelopes contain comparison schema/script versions, source inventory schema
version and timestamp, analysis timestamp, inventory directory fingerprint,
warnings, and records. Tests inject a fixed timestamp. Markdown is generated from
the same normalized records in stable order and contains no raw tenant payloads,
credentials, or stack traces.

## Security and logging

Tenant architecture and permissions metadata is sensitive. The comparator logs
only progress counts and output filenames; it must not print record contents,
site URLs, principals, IDs, permissions, or automation targets. Secret-like keys
and bearer-shaped values are rejected or redacted before output.

Synthetic fixtures use reserved example domains and invented identifiers. Live
inventories and generated gap reports must remain outside Git in approved storage.

## Human review gate

The output supports, but does not complete, IMS-003. The owner must review every
`Create new`, `Retire or consolidate`, and `Needs owner decision` result and all
permission, retention, automation, and inventory-quality findings. Provisioning
cannot begin until the field-level reuse/extend/retire matrix and target schema
are separately approved under the IMS decision gate.
