# IC-DEV-002 - Validated Feature-Branch Checkpoints

This authority update treats ordinary validated feature-branch checkpointing as
routine development work, not an owner escalation. It grants no general Git or
external authority.

The machine policy permits staging, committing and pushing only one completed,
reviewed roadmap increment whose relevant checks passed. Changed paths must be
increment-only, the message must match the increment, hooks and validation remain
enabled, and the material must contain no secrets, protected operational data or
live evidence. The only push target is the currently checked-out `feature/*`
branch's existing `origin` upstream. After push, local `HEAD` must equal the
upstream, and commit/push identifiers and outcomes must be recorded in
development state/audit without source content.

The policy permanently prohibits force and force-with-lease, protected/release
or different-remote pushes, merge, rebase, tag creation/deletion, branch
deletion, pushed-commit amendment, history rewriting, remote/upstream changes,
hook or validation bypass, protected-data commits and destructive recovery/reset.
Any missing, false, unknown or mismatched precondition fails closed as
`prohibited`; it does not become implicit authority.

This changes development checkpoint authority only. Authentication, live data,
production mutation, deployment, external communication and all existing owner
boundaries remain unchanged.
