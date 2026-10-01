# Accepted October EDN OS technical baseline

Date: 1 October 2026, Sydney. Owner: Elliot. [PR #2](https://github.com/elliot-daniels/edn-os/pull/2) was explicitly approved and merged normally, without squash or rebase.

| Identity | Exact value |
| --- | --- |
| Authoritative main merge | `c85938c44ef230b5e4574b084d709f263b92adc0` |
| Validated successor | `a81bda7bfa6674c767aeac607ec281da6fd980c0` |
| Frozen predecessor | `54b7326d755c253555d91febae1cfa4bdb5691e0` |
| Previous main parent | `5414dc10d6e92d36fa5c52811875cead5898d30e` |
| Merge and successor tree | `36009599fd9e05e4f2910c36d5dfd8e42565ee9c` |
| Hosted PR test commit | `27b3bfc44becd23f8bcd3c19b73a7d60b1f4b1e9` |

Main contains the exact successor as its second parent and all 160 preserved integration commits, including all six Operations commits. Both merge and successor trees match the tested tree. Separate UWC flow commits/assets remain excluded. Never reset or reconstruct main from a source archive.

[Hosted run 36867437110](https://github.com/elliot-daniels/edn-os/actions/runs/36867437110), attempt 1: all jobs succeeded. Linux 3.11: 1,089 passed, 0 failed/skipped, 9.53s. Linux 3.12: 1,089 passed, 0 failed/skipped, 10.73s. Windows 3.12: 997 passed, 92 unchanged baseline failures, no skips, 62.72s; signature guard passed. Linux lint/types/integrity/whitespace/clean-tree and Windows integrity passed. Independent review of `54b7326..a81bda7` found no actionable defect.

Compared with previous run 36863086924, ten inherited Linux fixture failures and 39 whitespace findings are resolved; 21 regressions were added. Windows has identical 92 failure identities/reasons; only the evidenced symlink terminal signature is now narrowly allowed. No new security, integrity or supported Linux protection failure was observed.

## Authority and limits

This is the accepted technical development baseline. Merge approval did not deploy, change production, approve live reads, renew grants, change Microsoft permissions or activate UWC flows. Every future merge needs current checks, independent review and Elliot's explicit approval. No standing autonomous merge authority is created.

The 92 Windows failures remain visible in `config/ci/windows-baseline.json`; a green guard is not a zero-failure suite or supported Windows protected-runtime certification. Synthetic ACL fixtures do not prove real NTFS security descriptors. Local native Windows typing retains 15 inherited errors in five files; offline IMS Pester retains three missing Add-PnPField mock-command failures. Python CI does not claim Pester/PST optional adapter or live Microsoft/production acceptance.

Historical development-state JSON, August grants and frozen UWC evidence remain unchanged; their branch/HOLD/expiry fields describe dated snapshots, not current main or active authority. CURRENT_STATE and this record establish the accepted repository baseline; runtime authorities retain their independent fail-closed controls.

## Future integration and rollback

New work starts from current main after verifying this merge is an ancestor, on one isolated issue branch. Record actual base/head SHAs. Branch names never replace exact-commit evidence. Revalidate any changed candidate/base. To undo an accepted change, propose an owner-approved revert preserving history and data compatibility; never reset main or activate an excluded branch. Repository protection settings are a separately approved owner decision tracked in issue #4.
