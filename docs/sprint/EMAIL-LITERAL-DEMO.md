# Fictional literal work-request demo

The opt-in email pilot adds Load fictional literal work request. It loads one complete fictional source with reported prose scope/site, labelled contact/customer/duration/reference and stable outer identity. Replaying retains the same draft and canonical job/hold. Embedded facts are email_reported, never verified customer records. No model or real source is read.

Demo: load the fictional request, review extraction/source details, click Prepare or refresh job, then Reserve synthetic provisional hold. The retained synthetic occupancy is visible after app reopen; loading again does not duplicate work. Approval, supporting upload and SharePoint dry-run/fake sync remain separate existing queue controls. No customer appointment or live sync is implied.

Two regressions verify fixture provenance and full-app load→prepare→hold→replay→reopen, with source/job/hold preservation and no automatic approval. Native Windows store case proves refusal only; hosted Linux required. No schemas, frozen QA, CI/security/authority changes. Review-only candidate; Android demo unchanged.

Linux/WSL actual private0700 Linux filesystem outside Git only, never Windows/DrvFs/real stores. Virtual environment, `python -m pip install -e ".[dev]"`, umask077, then `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`. Browser http://127.0.0.1:8502; restart omitting --initialise. Regression: `python -m pytest -q tests/ui/test_intake_literal_demo.py`. Broader extraction, AI fixtures/history reuse, source evidence promotion, thread/forward replay and autonomous coordination remain incomplete.
