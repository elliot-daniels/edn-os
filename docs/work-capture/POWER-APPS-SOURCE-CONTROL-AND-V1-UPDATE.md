# EDN Work Capture — source control and bounded V1 update

Status: **live scaffold exported; generated review source controlled; live V1 update not authorised; 29-field Work Log schema exists; UWC-AcceptCapture-v1 does not**

## Exact live app

| Property | Verified value |
|---|---|
| Display name | `EDN Work Capture` |
| App ID | `a47efc3e-0b52-405a-a220-54930a4ffdc9` |
| Environment | `EDN Systems (default)` |
| Environment ID | `Default-aae6ab79-45eb-4829-a04f-595becdb936d` |
| Runtime state | `Ready`; technical lifecycle `Published` |
| Sharing | zero users and zero groups |
| Current app version | `2026-08-21T02:20:45Z` |
| Data sources | SharePoint `Work Log`, `Projects`, `Clients` |

The API lifecycle value `Published` is a technical Power Apps state. It does
not mean the app has been promoted for operational use; the app is currently
unshared and remains a test scaffold.

## Supported source-control decision

Power Platform CLI `2.11.2` is installed. Its current canvas commands expose
`download`, `list`, deprecated/preview `pack` and `unpack`, an unavailable
`validate`, and `create`; there is no canvas upload/update command.

`pac canvas list/download` could not resolve this environment because the CLI
requires a Dataverse organization GUID or URL and the default environment has
no visible Dataverse organization. The existing PAC authentication profile was
therefore used only to call the documented read-only Power Platform API, locate
the exact app and download its current `document.msapp`. The archive was
verified as ZIP, SHA-256
`c555e598e1cb1e1c895c146d3f4742a55d141ce4f060dce76d5a2d045c18e56d`,
then extracted without `pac canvas unpack`.

Only `Src/App.pa.yaml` and `Src/Screen1.pa.yaml` are committed. Microsoft
identifies those generated files as the source-control surface; volatile JSON,
editor state and the temporary binary archive are excluded. Outside native
Power Platform Git Integration these YAML files are review source, not a safe
round-trip authoring surface. Major external YAML edits, `pack/unpack`, or an
invented upload API are not an acceptable update path.

For repository whitespace conformance, four trailing spaces were removed from
blank warning-comment lines in the generated files. The original export hashes
and normalized committed hashes are both retained in the baseline manifest;
no formula, control or property content was changed.

## Current scaffold verified from source

`Form2` is bound to `Work Log`, is in `FormMode.New`, and includes the canonical
`ProjectLookup` and `ClientLookup` cards. `WorkDate` defaults to `Today()` and
`TechnicalSummary` is the large `What did you do?` input. The visible mapped
fields are Hours, RateCode, Billable, TechnicalSummary, ClientLookup,
ProjectLookup, WorkType and TaskReference.

The source also exposes the unfinished parts precisely:

- the four current duration buttons all say `30m` and all write `0.5` hours;
- the form has no Submit control or success/failure/reset behavior;
- Project is positioned after the summary and commercial controls rather than
  first in the normal journey;
- Client is separately editable instead of derived/read-only from Project;
- Rate Code and Task Reference are always exposed;
- there is no Outcome field in the connected Work Log schema; and
- there are no capture/submission IDs or append-only correction fields.

The last two gaps mean the scaffold cannot yet meet the explicit canonical
Outcome, retry idempotency or correction-lineage invariants. Reusing invoice,
approval, legacy Project/Client text, RateCode, or another unrelated field for
those facts is prohibited.

## Bounded Studio V1 change set

Apply this change set only after the activation prerequisites below are
approved. Edit the existing app ID, not a similarly named copy.

1. Keep `Form2` bound to `Work Log` and `FormMode.New`. Remove the unused blank
   `Form1` only after confirming it has no formulas or references.
2. Reorder the ordinary path to Project (`DataCardValue9`), What did you do?
   (`DataCardValue7`), Duration, Outcome, then Submit. Put Work Type and
   Billable immediately below Outcome only when their project defaults require
   confirmation.
3. Make Client (`DataCardValue8`) read-only and populate it from the selected
   canonical Project relationship. Do not use legacy text fields.
4. Change the duration buttons to `15m`, `30m`, `1h`, and `2h`, with formulas
   setting `varHours` to `0.25`, `0.5`, `1`, and `2`. Add `Other` to reveal the
   numeric Hours input; keep the stored `Hours` value for compatibility.
5. Add Outcome from the approved `OutcomeStatus` field with fast choices
   Completed, Partial and Blocked. Do not simulate Outcome in another field.
6. Keep Work Type as the existing choice. Default Billable from the approved
   project profile; never infer it from a display name or change RateCode
   choices. Show Rate Code only for an approved relevant billing treatment.
7. Keep Task/Job Reference collapsed unless the applied project profile
   requires it or the engineer opens More.
8. Keep evidence and follow-up collapsed. Evidence must save to Project Files
   only after the canonical Work Log receipt, and secure/no-photo policy must
   suppress camera/photo controls before upload.
9. Add a full-width Submit control, at least 48 px high. It must call the
   reviewed idempotent acceptance flow with a submission GUID created once per
   entry; disable repeat taps while pending. Do not use direct `SubmitForm` as
   the final V1 acceptance boundary unless equivalent idempotency is proven.
10. On a typed success receipt, show `Saved` (or `Saved — evidence pending`),
    reset the form, generate the next submission key and focus Project. On
    failure, retain every entry and show `Not saved — your entry remains on
    this screen`.

## Activation prerequisites and stop point

Before Studio save/publish, owner approval must cover the existing activation
manifest and a concrete window, plus the minimum optional Work Log fields and
acceptance flow needed for Outcome, capture identity, idempotency, evidence
state and correction lineage. Project-profile defaults must resolve billing,
task-reference, evidence and secure/photo behavior without changing commercial
rates or webhooks.

No live app, SharePoint schema, flow, finance field, webhook, item or permission
was changed during this export. No customer record was read.

## Validation and phone handoff

After the approved Studio change:

1. run App Checker and resolve every formula, accessibility and delegation
   error;
2. preview Project → summary → duration → outcome → submit without creating a
   record until the synthetic test window opens;
3. save, publish, and re-export the exact app;
4. compare the new generated `Src/*.pa.yaml` files to this baseline and commit
   only the intended changes; and
5. open the app in Power Apps Mobile using the stable app ID, then submit the
   approved synthetic/non-customer scenario and verify exactly one Work Log
   receipt before testing retry, evidence or correction paths.

The stable play address is:

`https://apps.powerapps.com/play/e/Default-aae6ab79-45eb-4829-a04f-595becdb936d/a/a47efc3e-0b52-405a-a220-54930a4ffdc9?tenantId=aae6ab79-45eb-4829-a04f-595becdb936d`

## Microsoft tooling references

- [Canvas app source files and supported source-control surface](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/power-apps-yaml)
- [Current `pac canvas` command reference and deprecation status](https://learn.microsoft.com/en-us/power-platform/developer/cli/reference/canvas)
- [Power Platform API canvas-app listing](https://learn.microsoft.com/en-us/rest/api/power-platform/powerapps/apps/get-admin-apps)
