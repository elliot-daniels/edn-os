# Module 004 — Work

> **Knowledge Compounds.**

Status: **Approved for Universal Work Capture V1 only**
Module ID: `MOD-004`

## Purpose

Work owns durable records of meaningful work performed by EDN Systems. Its first
approved capability is Universal Work Capture: record a billable or
operationally/technically valuable unit of work once, retain its provenance, and
make it reusable by project history, follow-up, evidence, knowledge, time and
future commercial views.

This approval does not authorise the broader candidate scope of project
management, task management, deliverable management, asset management,
invoicing, deployment or live Microsoft mutation.

## V1 owned contract

MOD-004 owns:

- the source-neutral `WorkCapture` human-fact event;
- stable capture/submission identity and append-only correction lineage;
- work date/start, engineer, type, summary, outcome and duration;
- billing treatment and rate classification, but not price or invoice state;
- project/client references and applied project-default version;
- follow-up intent, but not the canonical Action record;
- evidence requirement/status and reference-only evidence relationships;
- secure-site and photo-policy enforcement at capture;
- human-marked Engineering Knowledge candidacy, but not knowledge approval;
- capture provenance and deterministic projection intents; and
- validation that does not require AI or a specific UI.

The existing SharePoint `Work Log` is the current physical source of truth for
the V1 event. MOD-004 owns the domain meaning; SharePoint remains the operational
database until a later approved architecture changes that boundary.

## Dependencies and consumers

- Identity/Microsoft authentication supplies the engineer principal; Work does
  not authenticate or invent identities.
- Existing Projects and Clients supply stable context/defaults; Work does not
  duplicate their authoritative business facts.
- Project Files or a confirmed evidence library owns binary content; Work stores
  references and evidence state.
- Actions owns follow-up records created from an explicit Work Capture
  projection key.
- Engineering Knowledge owns reviewed reusable knowledge; Work supplies only a
  draft candidate and source reference.
- Intelligence and Executive consume authorised references/derived views and do
  not rewrite Work facts.
- Commercial/Finance may later derive timesheet and invoice-preparation views;
  V1 makes no invoice, tax, payment or rate-schedule decision.
- Interfaces may implement Power Apps, web, API, import or voice entry against
  the same contract.
- Automation may execute projections only under separately approved external
  authority and must preserve idempotency, receipts and the canonical event.

## Invariants

1. One accepted submission key resolves to one canonical capture.
2. A retry cannot create a second Work Log item.
3. Different facts under the same submission key fail visibly.
4. Human-entered facts and later AI inference are stored separately.
5. Evidence is referenced; binary data is not embedded in the Work event.
6. Photo policy is independent of evidence requirement.
7. Required missing evidence becomes pending and never causes silent loss of
   the work fact.
8. Downstream facts are references, derived views, or deterministic create-once
   projections.
9. Corrections append and supersede; they do not erase the original.
10. Basic capture remains functional without AI, provider credentials or live
    Intelligence Core runtime access.

## V1 exclusions

- live Microsoft authentication, configuration or deployment;
- offline client-data storage;
- invoice generation or hard-coded commercial rates;
- payroll, expenses or finance authority;
- autonomous approval, action closure or knowledge promotion;
- location tracking, camera use where policy prohibits it, or background
  recording;
- project/task master-data ownership; and
- migration or destructive edits to current Work Log records.

## Implementation evidence

The approved contract and tests are in `src/edn/work_capture`,
`tests/work_capture`, `config/work-capture-v1-sharepoint-contract.json` and
`docs/work-capture`.

The 29 approved optional Work Log fields were created on 2026-08-21 and
verified by an immediate idempotency rerun. Site and list identifiers are
bound from the approved inventory. `UWC-AcceptCapture-v1` does not exist. The
2026-08-21T20:05:00+09:30 to 2026-08-21T21:30:00+09:30 flow-creation window
expired unused and is not reusable. No app submission path, capture, or live
SharePoint content integration exists.
