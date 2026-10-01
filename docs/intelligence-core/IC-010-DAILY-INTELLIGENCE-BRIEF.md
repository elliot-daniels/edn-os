# IC-010 — Daily Intelligence Brief

## Outcome

IC-010 adds a deterministic, user-invoked Daily Intelligence brief over the
existing permission-first context assembler. It adds no connector, permission,
scheduler, reasoning provider, or external action.

## Behaviour

- The brief returns zero to ten priorities from already-authorised evidence.
- Existing source-family balancing and stable ordering are retained.
- Every priority includes evidence IDs, confidence, a recommended next action,
  and explicit missing information.
- No evidence produces zero priorities and an explicit unknown statement.
- Unavailable capabilities remain visible gaps and are never invoked.
- The UI offers an explicit “Build today's brief” action.

## Security and validation

Composition receives only an assembled context and cannot query a source. The
canonical daily question changes no authority field. Automated acceptance tests
use local synthetic adapters only. IC-009 live Calendar authentication remains
owner-blocked.
