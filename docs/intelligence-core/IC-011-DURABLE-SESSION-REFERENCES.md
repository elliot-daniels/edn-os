# IC-011 — Durable Authority-Bound Session References

## Outcome

IC-011 adds a local SQLite session store that persists evidence identifiers and
the exact authority boundary required for follow-up turns. It stores no query,
excerpt, response body, prompt, or transcript.

## Authority binding

A persisted session binds to:

- principal and tenant identifiers;
- principal kind, delegation, and the full active-domain set;
- purpose and selected security domain;
- classification scheme and level; and
- normalized resource scope.

A changed boundary is rejected rather than merged. Session identifiers cannot be
reassigned to a different authority context.

## Evidence lifecycle

Saving a later authorized context reconciles evidence references atomically.
References absent from the new context become tombstones and are excluded from
the active reference set. A reference returned by a later authorized retrieval
may become active again. The store never resolves or copies source content.

## Persistence and validation

SQLite writes use an immediate transaction so the authority comparison and
reference replacement share one concurrency boundary. The schema is versioned,
uses foreign keys, and requires explicit initialization.

Synthetic tests prove restart continuity, authority-widening rejection,
tombstoning, safe reauthorization, and the absence of transcript-like columns.
