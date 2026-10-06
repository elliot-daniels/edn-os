# Calendar transport containment — synthetic implementation evidence

Base: authoritative main `c85938c44ef230b5e4574b084d709f263b92adc0`.
Scope: Calendar Graph transport only. Frozen Grok patches were unavailable in
repository/project artifacts searched during this session; existing repository
contracts and synthetic tests establish the behavior.

The default Graph GET opener rejects redirects. Authorization is an unredirected
header, and every GET validates the exact HTTPS Graph origin before acquiring a
token. Explicit ports, userinfo, fragments and control characters fail closed.
Responses are read with a 1 MiB bound and malformed/oversized pages are rejected.

Calendar event reads retain the exact metadata projection, a timezone-aware
positive window of at most seven days, and an integer cap of 1–25 records.
They perform one GET and ignore continuation links even if fewer records than
requested are returned, preserving the no-continuation contract recorded in
`MORNING-BRIEF-V2-PILOT-PROPOSAL.md`. Returned results remain bounded samples,
not evidence of exhaustive calendar coverage. Calendar identifiers are quoted
as a single path component; blank/dot identifiers and unsafe timezone headers
are rejected before authentication.

Calendar discovery retains its ten-page bound with 25 records per page. Before
following a continuation, it requires the exact Graph origin, unchanged resource
path and exact identity projection/page-size query plus one nonempty opaque
`$skiptoken`. A resource/projection/query drift fails before a second GET.

Synthetic transport tests cover bearer containment, default redirect handling,
origin attacks, query projection, windows/caps, overlarge/malformed pages,
bounded byte reads, one-page event retrieval and trusted/untrusted discovery
continuations. Existing admission, category, provenance and permission tests
remain unchanged. No live read, permission change or deployment occurred.

Validation: focused Calendar suite 48 passed; Calendar plus morning connector/opaque identity integration tests 73 passed; full Ruff passed; strict mypy with
Linux target passed for 135 source files. Full Windows suite and baseline guard
results are recorded in the PR. Linux runtime validation requires hosted CI;
Linux-target type checking is not a runtime substitute.

Rollback: revert the scoped feature commit. No data/schema migration is involved.
