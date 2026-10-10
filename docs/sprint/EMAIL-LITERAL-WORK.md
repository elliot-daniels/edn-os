# Bounded literal work-request extraction

Assessment version5 adds one local grammar: an unquoted current line `Please install|repair|replace <scope> at <site>.` Exact source scope/site substrings and the original line are retained as email_reported facts under the immutable outer Event identity. Existing classification/negation/competing-intent and explicit-forward gates still apply. No external model, semantic inference, verified-customer claim or duration estimate is added.

Multiple locations, conditional/alternative wording, hidden/control characters, conflicting labelled/literal fields and quoted history require clarification instead of choosing a value. The grammar is deliberately narrow, bounded by existing source limits plus scope500/site200. General natural-language extraction remains incomplete. Missing duration stays uncertain and cannot book automatically.

Older assessment versions1–4 remain readable/stale under the existing foundation. Materialisation/booking stays blocked until an explicit audited synthetic reassessment; original source and prior assessment remain. No real-store migration or automatic reassessment is authorised or performed. Database schema unchanged; accepted Android demo unchanged.

Thirteen new cases cover verbs/exact provenance, ambiguity/control/conflicts/history, canonical preparation with uncertain duration and retained version4/audited upgrade. Native Windows store cases prove refusal only; full hosted Linux required. Existing tests, frozen QA, CI/security/authority unchanged.

Linux/WSL only on actual private0700 Linux filesystem outside Git (not Windows/DrvFs/real stores). Virtual environment, `python -m pip install -e ".[dev]"`, umask077, then `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`; browser http://127.0.0.1:8502, restarts omit --initialise. Regression: `python -m pytest -q tests/operations/test_intake_email_literal_work.py`. Review-pending candidate, no deployment or live data.
