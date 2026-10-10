# Mobile review of stale synthetic holds

The opt-in email pilot adds a retained-hold selector and displays original occupancy plus current canonical job state, site and scope as inert text. A verified stale hold exposes a confirmation checkbox and guarded release action. The widget identity includes job content hash/revision and ledger revision, so a changed record resets confirmation before action. Current matching holds cannot release through this control. Aliased/malformed job/ledger evidence offers no action and keeps scheduling blocked.

Release invokes the existing guarded API and rerenders to the retained cancelled receipt; original plan/history/source/job stay intact. Cancelled holds remain visible for audit. No successful customer appointment, Microsoft event change or rescheduling is implied. No automatic job-action coupling is added.

Five full-app regressions cover edited/cancelled release and reopen/byte preservation, matching refusal, checked confirmation invalidation after another job edit, and corrupt job refusal. Native Windows validates protected-store refusal only; full hosted Linux required. No schema, frozen QA, CI/security/authority changes.

Linux/WSL on actual private0700 Linux storage outside Git only, never Windows/DrvFs or real stores. Use a virtual environment, `python -m pip install -e ".[dev]"`, umask077 and `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`. Browser http://127.0.0.1:8502; restarts omit --initialise. Prepare a synthetic source job and hold, then apply a synthetic update/cancellation; the review panel allows explicit stale occupancy release. Regression command: `python -m pytest -q tests/ui/test_intake_hold_review.py`. Review-only candidate; accepted Android demo unchanged.
