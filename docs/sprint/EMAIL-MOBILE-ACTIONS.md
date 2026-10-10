# Synthetic mobile update and cancellation controls

The opt-in email pilot exposes the existing audited update/cancellation APIs. Only current classified sources with a canonical request store display actions. Cancellation requires a clearly labelled checkbox. Server-side APIs independently refuse non-synthetic sources, ambiguity, unsupported changes, malformed stores and stale source revisions. Exact source replay preserves the durable receipt and does not add another revision. Approvals are invalidated by the existing API contracts.

Success identifies local revision/state, never delivery or confirmed appointment. Both controls explicitly warn that calendar reservations are separate and unchanged. Failure never reports success. This does not introduce automated ingestion, reservation coupling or live Microsoft access.

Regression: full-app controls exercise update/cancellation, unmatched refusal, confirmation gating, replay, source preservation, audit preservation and a fresh application session. Native Windows tests prove protected-store refusal only; hosted Linux is required for the actual app journey.

Linux/WSL synthetic launch, on an actual private Linux filesystem outside Git: create/activate a virtual environment, install `python -m pip install -e ".[dev]"`, then `umask 077`, create a 0700 private parent, and run `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`. Open http://127.0.0.1:8502. Restart with the same command omitting --initialise. Do not use native Windows/DrvFs or real stores. This candidate is review-only and must not replace the accepted Android demo without separate deployment authority.
