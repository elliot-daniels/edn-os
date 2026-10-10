# Canonical email answer approval barrier and UI preparation

This bounded follow-up to PR #55 makes the existing synthetic email view prepare
or refresh a canonical job. The field editor also permits the genuinely missing
email/phone required by the existing Job Requests contract. Incomplete fields or
unpromoted attachment metadata still refuse preparation. Approval, source review
and export remain separate existing Work Intake actions. No live transport exists.

The composed app passes its canonical request store when saving an email answer.
Under the draft lock, the request store first publishes a pending-source barrier,
records source-change audit and invalidates the source job and linked canonical
approval. Only then is the draft answer saved. After publishing the answer, the
canonical source projection refreshes automatically. Current canonical fields are
retained until explicit source review; old approved delivery is blocked throughout.

If draft publication is interrupted, the barrier survives restart. Old source
snapshots cannot clear it: source resolution refuses until preparation rereads
the current draft under its lock. An unchanged draft produces an audited recovery
receipt; a saved answer refreshes the source history. Explicit review is still
required to clear pending status. There is no success claim for an uncertain write.
Invalid canonical field values refuse before either store changes. Terminal jobs
cannot receive linked source answers. No new table/schema or destructive migration
is introduced; the existing protected snapshot/lock and audit contracts are reused.

Standalone `answer()` without a request store remains the partial-draft API for
unmaterialised records. Linked workflows must pass the canonical store, as the app
does. This is not an authorization boundary against an owner directly modifying
private stores or using other developer APIs. Other orchestration must use this
guarded path before claiming full workflow acceptance. Trusted identity matching,
attachment-byte promotion and coupled calendar reservation changes remain open.

Synthetic regression tests cover before/after approval invalidation, stale payload
denial, interrupted second-store publication, refusal to resolve old snapshots,
explicit recovery, unchanged approval after invalid input and terminal-state
refusal. A Linux AppTest uses the actual composed Work Intake application for
canonical preparation, answer correction and restart. Native Windows still refuses
protected storage. Hosted Linux/full Windows baseline gates and independent exact-
head QA/Dot acceptance are required; no main merge or Android replacement occurs.

Linux/WSL launch: follow `EMAIL-INTAKE-PREVIEW-DEMO.md`, run
`python tools/run_work_intake_demo.py --data-dir <private-Linux-root> --initialise --email-pilot`
and open `http://127.0.0.1:8502`. Supply missing contact fields, then choose **Prepare
or refresh job**. Review the resulting job in the existing Intake queue. Restart
with the same directory without `--initialise`. Use only synthetic data.
