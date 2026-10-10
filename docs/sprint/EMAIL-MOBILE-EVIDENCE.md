# Retained email evidence in mobile review

The opt-in synthetic email pilot adds **Show source details and change history**.
Alongside the existing immutable original body, the reviewer can inspect identity/hash,
exact extraction quotes and recent audited answer changes before preparing a job.
Embedded sender identities remain unverified. All source, quotes and audit values
use inert text widgets; source Markdown, images and HTML are never interpreted.

The view shows the most recent 20 history entries and explicitly reports the
total; no retained history is deleted. Original source and hash remain unchanged
after answers, and a fresh application can display retained evidence again.
This is read-only presentation: no storage/schema, classification, scheduling,
approval, transport, permissions or security policy changes.

Linux/WSL: use the existing private Linux directory and run
`python tools/run_work_intake_demo.py --data-dir <private-parent>/demo --initialise --email-pilot`.
Open `http://127.0.0.1:8502`, load fictional email fixtures and select the evidence
checkbox. Original body visibility is unchanged. Use an owner-private 0700 Linux
parent outside Git and `umask 077`; no
native Windows/DrvFs store. Restart with the same directory without `--initialise`.
AppTest proves actual UI text isolation and a fresh session, not Android physical
device interaction or host process restart. Independent exact-head Grok/Dot
acceptance and full hosted validation remain required. No change to the accepted
Android deployment, main or live Microsoft access is authorised.
