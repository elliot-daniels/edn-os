# Frozen previous public API for upgrade regression

These exact source blobs match PR51 head
34499e3eba3bb6fc691b4d7f657577f4ee358ebf. The manifest records SHA-256 and original
paths. They are test inputs only, never imported by application code. The nested
attribute preserves source bytes across Git checkouts so hash verification is
portable; no CI/baseline or frozen QA specification is changed.

The regression runs old ingest/answer in a separate Linux child process against
a fresh private synthetic store, then opens that unchanged database through the
current API. It proves source, answers and history survive the actual old-public-
API transition and audited reassessment; it is not a fabricated production store
or a data-reset workaround. The old classifier is bound only inside that child.
