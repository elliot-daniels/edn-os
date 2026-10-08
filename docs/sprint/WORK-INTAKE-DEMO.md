# Work Intake synthetic demo candidate

This candidate is under validation. It is not yet an accepted complete MVP.
Use a new synthetic-only directory; do not open or migrate an operational store.
Native Windows deliberately refuses before storage access. Under WSL, run from
the Linux filesystem; `/mnt/c` and other DrvFs roots are rejected even with metadata.

## Launch on Linux or WSL

From the exact reviewed candidate checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
install -d -m 700 "$HOME/edn-synthetic-demo"
python tools/run_work_intake_demo.py \
  --data-dir "$HOME/edn-synthetic-demo/work-intake" --initialise --port 8502
```

Open `http://127.0.0.1:8502`. The server binds loopback only. Stop with Ctrl+C.
For subsequent launches omit `--initialise`; do not replace the directory with a
real store. The existing private parent is required so initial creation cannot
follow an unchecked path. Dependencies are development dependencies already used
by EDN OS, with no paid service or live integration required.

## Demonstration journey

1. Enter a synthetic manual request. The submission identity is persisted before
   saving; retries retain it. Start a new work request explicitly for a second job.
2. Save a supporting file. PDF, PNG, JPEG, DOCX, EML and TXT are supported. Limits
   are decimal20,000,000 bytes/file and100,000,000 bytes/request; zero bytes reject.
3. Select the request in the unified queue; correct its details. Evidence stays
   local and untrusted; the app does not claim OCR extraction or malware cleaning.
4. Review and self-approve. Approval binds the exact revision/content hash; later
   edits or evidence changes invalidate approval and are audited.
5. Prepare the reviewed dry-run record. Download the complete evidence manifest
   and expected-schema validation envelope. Live schema remains unverified.
6. Run the local synthetic transport with failed or unknown outcome. Unknown
   blocks another delivery until explicit reconciliation. A synthetic synced
   result still displays live SharePoint not synced.
7. Import the synthetic website fixture only after the refreshed source adapter
   and combined candidate pass review. Source items must reference their existing
   identity; they must never produce a second SharePoint create proposal.

## Validation limits

Local Windows checks exercise pure contracts and native refusal only. They do not
prove supported-runtime persistence or the complete journey. Hosted Linux tests,
exact-head independent QA, refreshed source handling and composed UI tests are
required before this candidate can be called complete. No live SharePoint write,
deployment, real database migration, credential change or main merge is authorised.

## Direct QA remediation checkpoint

F45-01: the sender freezes its own bounded JSON snapshot and rechecks current
approval/evidence under the intake lock through publication. F45-02: existing
website records remain reference-only; item delivery is disabled in the UI and
refused by the service, including forged create operations. F45-03: documented
normalised current/original identifying-fact candidates require explicit reasoned
duplicate decisions. F45-04: approved queue labels show `(self-approved)`.

F45-05 remains an owner scope decision: no authoritative customer/project
association catalogue exists in this MVP. Company/reference are free text and
must not be described as an association authority. Existing NOW scope excludes a
new CRM relationship catalogue. Neither catalogue creation nor exclusion from
the frozen association criteria is inferred from QA; an explicit owner decision
is pending. Product acceptance remains HOLD until that decision and exact-head
independent acceptance are recorded. The frozen specifications are unchanged.
