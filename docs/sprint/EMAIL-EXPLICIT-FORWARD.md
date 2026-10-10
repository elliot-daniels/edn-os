# Explicit synthetic forwarded request preparation

This bounded extension accepts one labelled forwarded request when the current
body contains only an explicit instruction such as “Please prepare the forwarded
work request.” The supported envelope is one Forwarded message or Begin forwarded
message marker, unique conventional headers including Subject, a blank separator
and an unquoted body. A malformed envelope, nested history or competing intent
does not supply scheduling facts. Ordinary forwards remain non-actionable.

The embedded From, To and Date are untrusted text. They never establish sender
identity, verified customer contacts, authority or duplicate identity. Extracted
labelled values remain email-reported facts with exact source quotes and the outer
Operations Event identity. Explicit customer dates and night times are preserved.
No external AI, mailbox read, appointment or SharePoint write occurs.

Assessment version advances from 3 to 4. Previous receipts retain original source,
hash, answers and audit history and become stale until explicit audited synthetic
reassessment. No real-store migration or deployed-demo upgrade is authorised.
Existing required canonical fields, approvals and protected storage are unchanged.
This is not general unstructured extraction, forwarded-message deduplication or
verification that the embedded sender actually sent the message.

Linux/WSL: install the existing development dependencies, then run
`python tools/run_work_intake_demo.py --data-dir <owner-private-linux-parent>/demo --initialise --email-pilot`.
Use a private 0700 parent outside Git with `umask 077`, not a Windows/DrvFs path.
Open `http://127.0.0.1:8502`, choose **Load synthetic forwarded request**, inspect
the source and choose **Prepare or refresh job**. Existing queue review, supporting
upload, self-approval and SharePoint dry-run export remain separate steps. Restart
with the same data directory without `--initialise` to check persistence.

The new AppTest covers the actual load/preparation/replay UI and a fresh app
session. It does not prove a physical mobile upload picker or host process restart.
The accepted Android demo remains unchanged. Independent exact-head Grok QA and
Dot technical acceptance are required before accepted development integration.
