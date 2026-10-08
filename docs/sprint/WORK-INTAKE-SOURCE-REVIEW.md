# Synthetic source intake and explicit duplicate review

This stacked change depends on the protected core and manual submission receipts.
It reads caller-supplied synthetic contract1.0 mappings only, with a bounded explicit
source identity: source_system (sharepoint), source_account, site_id, list_id and
native_item_id. external_id must equal that native item ID. The identity tuple,
not Title, CustomerReference or content, defines replay identity. No HTTP, tokens,
permissions, source writes or scheduler are present.

First intake atomically retains immutable source JSON/history and a distinct local
draft/receipt. Equal canonical source facts replay the current local review state.
Changed source facts append a source revision, mark explicit pending review and
invalidate prior approval with an audited local revision; existing corrections and
attachment associations remain intact. keep_local/apply_source requires a bounded
operator reason and exact local revision. Rejected/cancelled work does not become
an approved job by reimport; approval/export is blocked while source review is pending.

Possible duplicate work uses a versioned identifying-facts fingerprint over company,
contactName, siteLocation, reference and preferredDate, in that fixed order. Each
value undergoes Unicode NFKC compatibility normalization, case folding and Unicode
whitespace collapsing. The domain-tagged canonical JSON tuple is hashed with SHA256
(`possible-work-v1`). Description, urgency, email and phone do not control this
conservative possible-work signal. Both the current reviewed facts and the immutable
original submission facts are compared, including current-to-original matches;
a correction that introduces a match therefore blocks approval until resolution.
This fingerprint is only a candidate signal: request UUIDs, source identity tuples
and submission keys remain authoritative and independent. No automatic merge or
identity deduplication occurs. Approval/export requires an
explicit distinct-work or same-work resolution. Decisions retain actor, UTC time,
reviewed revisions and hashes. Same-work links an alias to a canonical local work
key, invalidates canonical approval and prevents independent alias approval/export.
A group containing imported work exports reference_existing with the actual native
source identity; mapped fields remain review metadata and never authorize creation.
No fake EDN-JR identifier or invented SharePoint columns are introduced.

Explicit initialization adds version3 source/history/duplicate/link tables to a
compatible synthetic receipt store. Old source revisions/receipts/review audits
remain intact, failed upgrades preserve the snapshot. No real-store migration or
production readiness is claimed. Rollback disables the dependent import UI and
preserves the local store; no destructive downgrade occurs. Full hosted CI and
exact-head independent source-change, cross-source and corruption QA are required.


Operator editing, lifecycle, approval and export actions belong to the canonical
work request. Linked aliases are retained provenance references: cancelling,
rejecting or reopening an alias is refused without mutation. Source review on an
alias remains available while its canonical request is legally active. A terminal
canonical request is never reopened by source intake or duplicate resolution;
rejected work requires an explicit audited reopening, and cancelled work remains
terminal. New linkage must name the actual canonical target, not another alias.


Distinct-work decisions remain bound to each request's exact current revision and
full normalized fields plus evidence content hash. Even an edit to description or
urgency invalidates that decision's bypass; fingerprint similarity alone cannot
reuse an old resolution. Reasoned review preserves independent same-content jobs.
