# Main protection proposal — pending Elliot decision

This is a reviewable proposal for issue #4, not an applied settings change. Hosted CI is established; current required-check/reviewer/owner-merge enforcement is manual. No account, token, role or permission changes are authorized by this document.

Proposed target: `main`. Require PRs and one independent review; dismiss stale approvals after new commits and require resolved review conversations. Require current-head successful checks `Linux synthetic validation (3.11)`, `Linux synthetic validation (3.12)` and `Windows baseline regression guard`, with the branch up to date or a separately accepted tested merge queue. Preserve normal merge commits; do not require linear history for this repository. Block force pushes and deletion. Do not add an automatic deployment or automatic merge rule.

Elliot must decide which actual GitHub identities may merge and which bypass privileges, if any, remain. Dot and Grok are role names, not verified account identities. The policy requires Elliot's explicit approval per merge even if GitHub considers a PR technically mergeable. A comment from an AI using Elliot's account is not proof of independent human approval. Separate agent accounts and limited development access require Elliot's own account/access decisions; no Global Admin or live production access is needed.

Before application, verify availability under the repository's plan and current rules, document any conflicting rules, confirm check names on a fresh PR, and present the exact proposed settings to Elliot. Do not promise settings the GitHub plan cannot enforce. After approval, verify effective rules with read-only evidence and use a synthetic PR to demonstrate rejected unchecked/unreviewed updates. Record the applied scope, actor, time, evidence and limitations. Rollback is an Elliot-approved settings reversal, never a history rewrite.

Until then: no direct main edits; one claimed issue/isolated branch; all current checks; independent review of exact head; explicit Elliot merge decision; normal merge preserving ancestry. Protection controls repository integration only and confer no runtime/live-source authority.
