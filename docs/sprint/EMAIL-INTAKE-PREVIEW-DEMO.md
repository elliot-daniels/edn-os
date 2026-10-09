# Synthetic email intake preview in Work Intake

This opt-in view uses the existing app and protected partial-draft store. Six
fictional emails include two new jobs, financial correspondence, general
information, follow-up and uncertain intent. Source quotes, classification,
operator corrections, missing-field categories and audit history appear in the
intake page. Repeated fixture loading retains records and answers.

Scheduling previews use an explicitly empty **synthetic** calendar. No authorised
live availability was checked and no reservation, customer appointment, message
or SharePoint record is created. New jobs can receive a preview; ordinary
correspondence cannot. Missing duration uses a visibly unverified 60-minute
planning estimate and remains proposal-only. Explicit duration and site may make
a proposal eligible, but eligibility is not execution. Date/time parsing preserves
night work and refuses invalid/ambiguous Adelaide DST wall times. A time without
a date requires clarification rather than choosing a date silently.

## Linux/WSL launch (development candidate only)

Install the candidate's existing Python dependencies in a virtual environment.
Use a new private synthetic data directory outside Git, on the Linux filesystem,
not a Windows/DrvFs mount. Example with an owner-private home directory:

```sh
umask 077
mkdir -m 700 "$HOME/edn-email-pilot-parent"
python tools/run_work_intake_demo.py \
  --data-dir "$HOME/edn-email-pilot-parent/demo" --initialise --email-pilot
```

Open **http://127.0.0.1:8502**. In Intake queue, choose **Load synthetic email
examples**. Inspect the two jobs and negative examples, answer a missing duration
with `90 minutes`, stop/restart using the same data directory without
`--initialise`, then confirm answers and history persist. Default app launch
without `--email-pilot` retains the existing interface. No deployment replacement
is authorised by this candidate; the working Android host remains unchanged.

This is a preview, not complete unattended email intake. Attachment ingestion,
trusted historical/customer lookup, materialisation into canonical reviewed job
records, cross-forward/thread deduplication, update/cancel reconciliation and
atomic synthetic reservation publication remain required. No real-email accuracy
claim is made.

## Validation boundary

Fourteen pure scheduling-preview cases cover negative correspondence, answer
continuation, estimated duration, night requirements and invalid/ambiguous local
times. The AppTest journey covers load, correction, fresh application and replay.
Locally, Windows sandbox AppTest was blocked before the application script ran:
Python asyncio's loopback `socketpair` fallback stalled in `socket.accept` while
constructing Streamlit LocalScriptRunner. A diagnostic faulthandler trace located
that boundary. No timeout was increased or assertion skipped. Full hosted Linux
and Windows CI must validate this exact head in a fresh environment.
