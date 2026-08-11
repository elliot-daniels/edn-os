# IC-012 — Internal Proposed Actions and Draft Review

## Outcome

IC-012 extends Intelligence Core responses with evidence-bound internal proposed
actions and drafts. It adds no executor, external provider, production write
path, or runtime permission grant.

## Proposal and lifecycle

Each proposal records its identity, authority scope, proposed operation, target,
evidence, rationale, confidence, outcome, risk, reversibility, required permission
and approval, optional draft, timestamps, status, exact hash, and review reference.

“What should I do?” creates an internal proposal. “Draft it for me” creates an
internal draft awaiting review. Review decisions bind to the exact proposal hash.
Approval also requires current authorised evidence and an unexpired proposal.
Editing supersedes the old proposal; approval never carries forward.

The internal lifecycle supports proposed, draft, awaiting review, approved for
execution, rejected, superseded, and cancelled. Executed and failed are reserved
for a future separately authorised executor. IC-012 rejects both transitions and
exposes no execution method.

## Persistence, UI, and security

In-memory and SQLite stores preserve proposal/review state. The Intelligence UI
shows the rationale, draft, target capability, risk, and an explicit notice that
nothing was sent or executed and owner execution approval is required.

Proposal creation is not execution permission. Development approval is not
runtime approval. Cross-domain, removed, unauthorised, expired, or materially
changed evidence fails closed. External communication, Calendar or SharePoint
mutation, financial actions, production writes, shell actions, and permission
changes remain unavailable.
