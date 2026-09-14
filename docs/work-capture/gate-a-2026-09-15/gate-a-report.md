# EDN UWC Gate A — blocked diagnostic checkpoint

Prepared 2026-09-15 Australia/Sydney. Gate A is **not complete**. Gate B is **not authorized or executed**.

## Requested results

1. **Root cause:** not proven. The exact Add flow error reproduced in a fresh Studio session. The disabled flow is a candidate cause, but turning it on to test that hypothesis is prohibited. Dataverse also demands password verification, preventing further solution metadata inspection. These are distinct issues; neither is presented as a proven root cause.
2. **Corrective action:** no Microsoft configuration change was saved. Inspected the existing app, V2 trigger, solution identity, owner, connection reference, run-only settings and checkers. Retried Add flow once in a fresh session; it failed.
3. **Binding:** failed for Developer app `eb306bf3-a897-455c-abc9-a3c4f51da858` and flow `c648c824-55a6-f111-b8de-002248991d3a`. New diagnostic session: `88be42db-828d-40ef-ba45-2d6880e96db6`. Studio's flow pane remained empty; the flow detail page showed no associated apps. The associated-apps panel alone is not treated as proof of runtime binding.
4. **Checkers:** Flow Checker: 0 errors, 1 warning (`This flow is off`). App Checker: no formula findings, 16 accessibility findings, 2 unused-data-source warnings (`Projects`, `Clients`). These are pre-repair results, not final acceptance.
5. **Flow state:** Off; UI explicitly reported it had not been run. Observed 2026-09-14 UTC. Never enabled or invoked in this session.
6. **Work Log:** exact list `7b6d10ec-c009-422a-9802-c907d3d4f57f` returned `ItemCount=0` by authenticated, read-only SharePoint REST navigation, matching Site Contents.
7. **Microsoft-side changes:** none saved. No app publishing, flow saving, permission changes, record writes, emails or messages. Opening Studio and a failed binding attempt may generate service telemetry; no successful binding is claimed.
8. **Default environment:** not opened or modified in this session. Its app and historical flow were not edited. The shared SharePoint site was read only.
9. **Hashes:** final live workflow and authentic post-binding solution ZIP hashes are unavailable. The checked-in Git blob workflow SHA-256 is `c07db6251e55a6242c5b883cdd2a9c636e2237c4d7db8411983213d224259397`. The existing Windows worktree bytes hash to `44debaedd83e15c62604acafbf04dbd40e5f6c4a4420099b8cdfc3705149b659`; line-ending representation differs. Neither is labelled the final live workflow hash.
10. **Repository:** reviewed local and remote branch head was `4f76f915c14a26c6f2c52c2557cce9b16b1b2f64`, `feature/uwc-solution-scaffold`. No completed Gate A result exists to push. Any diagnostic-only commit must remain clearly marked blocked.
11. **Manifest:** `gate-a-diagnostic-checkpoint.json` is a blocked evidence snapshot, **not** the frozen Gate A runtime manifest. Six prepared cases are in `gate-b-unexecuted-payloads.json`.
12. **Unresolved risks:** listed below. No runtime assertion has been validated by executing a payload.
13. **Gate B approval:** do not issue a Gate B GO against this checkpoint. A final approval prompt cannot yet bind to a successful Gate A commit, authentic ZIP hash and final live workflow hash. The review draft below must be completed only after Gate A succeeds.

## Verified identities and fixtures

- Environment: EDN UWC Development / `0813c3a4-765f-eafe-9a6a-05ebf0521bc6`.
- Solution EDNUWC: `2a8fa4f7-f5a5-f111-b8de-002248991d3a`, unmanaged, version 1.0.0.0 in the portal. Flow detail page lists EDN UWC membership.
- Developer app: `eb306bf3-a897-455c-abc9-a3c4f51da858`, owned by Elliot Daniels; standard license designation; saved unpublished state when opened.
- Flow owner: Elliot Daniels. EDN UWC SharePoint resolves in the flow UI to `elliot@ednsystems.com.au`. Run-only mode is `Provided by run-only user`; no additional run-only users were listed. Exact Dataverse connection ID remains unexported.
- Project ID 4: `[SYNTHETIC UWC V1 ACCEPTANCE] Secure Project`, `SYNTH-UWC-ACCEPT-01`, Active, Client lookup 5, `Secure Client - No Photos`.
- Project Modified: **2026-09-08T07:06:00Z**, verified directly from the item REST response; not inferred from a locale-rendered time.
- Client ID 5: `[SYNTHETIC UWC V1 ACCEPTANCE] Client`; Modified `2026-09-08T07:03:39Z`.
- Prepared payload policy: secure=true, photos=prohibited, non_billable, empty rate code, no attachments, no follow-up/evidence record creation.
- `Administration` was verified among live WorkType choices.

## Investigation limits and review findings

**Access:** Dataverse displayed “Because you're accessing sensitive info, you need to verify your password.” The user must complete this sign-in; no password is requested in chat. PAC's installed path remained inaccessible to the shell even after a scoped filesystem grant. A standard NuGet metadata request failed TLS authentication; certificate checks were not disabled. These constraints prevented PAC export/pack/unpack validation.

**ALM reconciliation:** the repository's flow trigger name is `manual`; the current designer names it `When_Power_Apps_calls_a_flow_(V2)`. The two required text fields and concurrency=1 match. This proves the reviewed source cannot simply be called an authentic final export. The source-controlled solution lacks the Developer canvas app component. The historical imported app package carries `isSolutionAware=false`, but that historical flag does not establish current membership. Inspect live dependencies after sign-in; do not manufacture app metadata or edit the default app.

**Environment variables:** four repository workflow defaults target the EDN site and Work Log/Projects/Clients list GUIDs. Their live Dataverse current values, deployment mappings and asynchronous connection-reference resolution still need verification. Repository defaults are not evidence of effective live resolutions.

**Receipt URL defect:** the repository uses `/Lists/Work%20Log/DispForm.aspx?ID=` in saved and replay receipt paths. SharePoint REST returned RootFolder `/sites/EDNSystems/Lists/WorkLog`; the spaced list path returned 404. Reconcile against the live export and correct the flow through the established ALM process before claiming working receipt links. No flow edit was made merely to fix this unrelated binding issue.

**Replay:** the source's `Repair_existing_engineer` branch uses PatchItem if Engineer is missing. “Replay makes no writes” is conditional on the existing item already being complete. Gate B must check item versions/content, not just item count.

**Ambiguous create:** the source catch block reports “Not saved” and clears receipt fields even if create already succeeded and a later read/patch failed. Any such result requires read-only lookup by the same submission key; stop before any fresh-key retry.

**Validation coverage:** 39 existing Work Capture tests passed. Those tests do not establish Microsoft workflow runtime correctness. All 1 JSON and 7 XML files in the solution parsed. Each of the 6 prepared payloads matched required names and basic types in the repository ParseJson schema. This is not execution of WDL expressions, SharePoint validation, policy acceptance or a successful PAC round trip.

## Safe next steps

1. Complete the open Dataverse sign-in, restore supported PAC access, inspect current app/flow/solution membership, effective environment variables and connection-reference IDs, and obtain an authentic pre-change export.
2. Diagnose the binding service failure from supported Microsoft diagnostics. Retain the existing app, flow, reference and invoker mode. Do not turn on the flow under the current authority. If activation is demonstrated to be necessary, present that as a separate Gate A boundary decision; activation-only approval must not authorize runtime payloads.
3. After an authorized successful repair, save the binding as needed, recheck it from both Studio and an authentic solution export, run both checkers, reconfirm Off/0 and Work Log=0, reconcile source, run PAC round-trip and repository validation, and calculate final hashes.
4. Resolve or explicitly review the receipt and runtime risks. Freeze the complete Gate A manifest and commit/push the validated result to the named feature branch. Never merge or create a PR.

## Gate B execution plan — review only

After a separate, exact owner approval, revalidate all frozen identities, hashes, fixture timestamps, connection mappings, Off/0 and Work Log=0 before enabling anything. Abort on drift. Run the prepared cases sequentially: new, exact replay, conflict, policy mismatch, stale profile, correction. Expected new item deltas are 1, 0, 0, 0, 0, 1. Verify status, immutable facts, item versions, policy, receipt links, and correction linkage after each case. Stop immediately on mismatch or ambiguous results, preserve records, and reconcile read-only. Return the flow Off at the end. No additional fixtures, files, permissions, messages, operational/customer changes, finance changes or default-environment changes.

**Owner-approval draft (not ready to issue):**

> GO — authorize only the six synthetic Gate B cases in the reviewed frozen Gate A manifest, bound to its exact repository commit, workflow SHA-256 and authentic solution ZIP SHA-256, during the explicit execution window recorded in my approval. Use only Developer app eb306bf3-a897-455c-abc9-a3c4f51da858 and flow c648c824-55a6-f111-b8de-002248991d3a in environment 0813c3a4-765f-eafe-9a6a-05ebf0521bc6, Client 5 and Project 4 with Modified 2026-09-08T07:06:00Z. Permit temporary flow enablement and only the new/replay/conflict/policy-mismatch/stale-profile/correction payloads frozen in that manifest, with at most two synthetic Work Log creations. Verify read-only after each case, stop on drift or ambiguity, preserve all records, and return the flow Off. Preserve every other hard boundary from the Gate A request. This draft is ineffective until the final manifest path, commit, hashes and execution window are explicitly supplied and approved.

## Microsoft documentation used

- [Known Power Apps V2 trigger issues](https://learn.microsoft.com/en-us/troubleshoot/power-platform/power-automate/flow-creation/known-issues-power-apps-v2-trigger): V2 supports embedded and invoker connections; connection changes require app metadata refresh/rebinding. This does not prove the observed error's cause.
- [Connection references](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/create-connection-reference): inspect effective connection mappings and solution membership; do not assume adding an outside app/flow upgrades every connection.
- [Troubleshoot flow integration](https://learn.microsoft.com/en-sg/troubleshoot/power-platform/power-apps/connections/best-practices-when-updating-a-flow): multiple metadata/authorization failures can affect integration. No specific backend error code was exposed by the observed Add flow dialog.
