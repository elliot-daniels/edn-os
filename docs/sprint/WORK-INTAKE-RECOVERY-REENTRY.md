# Interrupted recovery: first-reopen cleanup

Base implementation: accepted b4a519bd2ee0da555005c8b6c1f55fdcbd18bf45.
PR48 isolates this repair; the existing private Android demo is unchanged.

Hosted regression-only head00fac22d535c97646f81106b89dd181c9be4f6e6,
run37992012483, reproduces on Linux3.11 and3.12. Both one and three real subprocess
exits after quota-stage fsync/before replacement make completed evidence
unreadable on the first normal reopen. Each suite has exactly2new failures,
1720existing passes. The earlier initial fixture used duplicate bytes and failed
before reaching recovery; it is not reproduction evidence.

Cause: a resumed journal records moves before its own interrupted quota staging.
Replaying that plan leaves those later stages outside its saved move list.
Repair completes the saved plan first, then makes one fresh bounded sweep when
resuming. Existing validation, file/directory limits, descriptor anchoring,
quarantine and quota rules remain unchanged. No recursion, deletion or retries
of live operations are introduced.

Regression requires completed get/read, exact remaining quota entries, preserved
incomplete original bytes in quarantine, no residual quota/journal in the request,
and a byte-identical second reopen. Fresh full hosted validation and independent
edn-grok-qa exact-head acceptance are required before integration or replacing
the approved demo. No frozen QA specifications/baselines/timeouts were changed.
