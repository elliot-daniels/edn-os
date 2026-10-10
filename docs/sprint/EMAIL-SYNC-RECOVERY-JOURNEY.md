# Synthetic sync recovery through the email app

Two full-app regressions exercise approved email work with supporting evidence and the actual reviewed UI envelope. A failed fake transport persists across a fresh session and allows a safe successful retry. Unknown acknowledgement persists, blocks blind retry and requires explicit reconciliation. Neither case represents live SharePoint success.

The approved payload, original email, approval audit, supporting bytes and historical attempt remain. Reopening and re-preparing uses the same exact envelope. Reconciliation of unknown does not perform another fake delivery; retry of known failure is attempt2. Subsequent confirmed replay does not increment the attempt or duplicate work. No product changes or network/provider calls.

Native Windows store cases establish platform refusal only; hosted Linux validates the actual app/store flow. AppTest does not drive a physical upload picker or prove host crash recovery; supporting wrapper invokes the real handler, and fresh AppTest proves app-session persistence. Existing process-death tests remain separate. No frozen QA/CI/security/schema/authority changes.

Linux/WSL actual private0700 Linux filesystem outside Git only, never Windows/DrvFs/real stores. Virtual environment plus `python -m pip install -e ".[dev]"`, umask077, then `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`. Browser http://127.0.0.1:8502; restart omitting --initialise. Regression: `python -m pytest -q tests/ui/test_email_sync_recovery_journey.py`. Review-only candidate; accepted Android demo unchanged. Full autonomous intake/extraction/history reuse/source attachments/thread reconciliation remain open.
