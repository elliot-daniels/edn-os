# Composed synthetic email job evidence journey

This verification-only PR follows the guarded canonical preparation candidate.
It changes no application, storage, schema, CI, security policy or frozen QA files.
Independent acceptance is still required for the exact composed candidate.

The actual Work Intake app is tested through canonical email-job preparation,
supporting TXT upload, approval, SharePoint dry-run export, identical-file replay,
source correction, explicit source review, fresh approval/export and a fresh app.
Evidence bytes, file-to-job association, manifest hash, stable submission key,
original email/hash and revised approved content hash are checked. An empty upload
must fail without changing the job or source. Source corrections must invalidate
the old approval and preserve supporting evidence. No remote delivery is performed.

AppTest does not operate a physical browser file picker. The test provides a
synthetic upload object to the actual `st.file_uploader` handler; protected file
validation, storage, canonical association, buttons and approval/export logic are
real. Fresh AppTest means a new application/session, not a host process restart.
Existing protected-store and process-recovery tests provide separate persistence
evidence. This test does not establish Android camera/PDF picker behavior or
simultaneous-user acceptance. Native Windows proves protected-store refusal only.

The file is supporting evidence uploaded by the local operator, not a verified
attachment from an original email. The source fixture contains no email attachment
metadata. Original email attachments remain unpromoted and block canonical
materialisation until source-to-byte association is implemented; nothing is omitted
or mislabelled as a downloaded email attachment. General forwarded extraction,
trusted matching/execution and coupled provisional reservations remain incomplete.

Linux/WSL demonstration, synthetic data only:

1. Install the candidate's existing development dependencies in a Python venv.
2. Under an owner-private Linux home, create an outside-Git parent directory with
   `umask 077` and mode 0700. Do not use a Windows/DrvFs directory.
3. Run `python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`.
4. Open `http://127.0.0.1:8502`, load the synthetic emails and fill missing contact
   name, email and phone. Choose **Prepare or refresh job**.
5. In the existing Intake queue, select the job and upload a synthetic supporting
   file. Review and approve, then prepare the SharePoint dry-run record.
6. Correct an email answer. Review the changed source in the queue, approve the
   new exact revision and prepare another dry-run record. Evidence must remain.
7. Stop/restart with the same directory without `--initialise`; verify the job,
   evidence and audit history remain. Restart testing on the host is an operator
   check and is not claimed by the new AppTest alone.

The existing private Android demo remains unchanged at its accepted commit. No
candidate deployment, live Microsoft access or main promotion is authorised here.
