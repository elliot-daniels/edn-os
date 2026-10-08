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

Identical initial fields across independent keys are only potential duplicate
candidates; requests and provenance remain distinct. Approval/export requires an
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
