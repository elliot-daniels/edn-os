# EDN Work Capture V1 — ordered Power Apps Studio runbook

Status: **manifest-bound Work Log fields exist; `UWC-AcceptCapture-v1` does not. Do not execute this runbook. The 2026-08-21T20:05:00+09:30 to 2026-08-21T21:30:00+09:30 flow-creation window expired unused and is not reusable**.

This runbook edits the existing app only:

- app: `EDN Work Capture`
- app ID: `a47efc3e-0b52-405a-a220-54930a4ffdc9`
- environment: `EDN Systems (default)`
- environment ID: `Default-aae6ab79-45eb-4829-a04f-595becdb936d`
- exported baseline: `config/work-capture-power-app-baseline.json`
- baseline controls: `power-platform/work-capture/canvas/EDNWorkCapture/Src/Screen1.pa.yaml`

Do not import the generated `.pa.yaml`, use `pac canvas pack/unpack`, create a
replacement app, or change the app ID. All formulas below use the exact existing
control names. A control whose name begins with `uwc` is inserted in this runbook
and renamed immediately so later formulas remain unambiguous.

## Gate before opening Studio

Do not begin the edits unless all of these are true:

1. `Work Log` contains the exact optional fields in the approved manifest.
2. `UWC-AcceptCapture-v1` exists in the same environment and has exactly two
   Power Apps (V2) text inputs, in this order: `submissionKey`, `payloadJson`.
3. Its response has text outputs `status`, `captureId`, `workLogItemId`,
   `workLogItemUrl`, `evidenceStatus`, and `message`.
4. `status` is one of `saved`, `already_saved`, `conflict`, or `rejected`.
5. The flow derives the engineer from the invoking connection, checks the
   project and policy server-side, treats the same key/same facts as
   `already_saved`, rejects the same key/different facts as `conflict`, and does
   not clear or overwrite the earlier capture.

If any gate fails, close Studio without saving. The current activation receipt
records that the Work Log schema gate has passed and that `UWC-AcceptCapture-v1`
does not exist. The previous flow-creation window expired unused and is not
reusable.

## 1. Open the exact app and refresh bindings

| Step | Select | Property/action | Exact value or action | Expected result |
|---:|---|---|---|---|
| 1.1 | Power Apps maker portal | Environment | `EDN Systems (default)` | The environment ID shown is `Default-aae6ab79-45eb-4829-a04f-595becdb936d`. |
| 1.2 | Apps > `EDN Work Capture` | Edit | Open the existing app; do not use **Save as**. | The tree contains `Screen1`, blank `Form1`, and `Form2`. |
| 1.3 | Data > `Work Log` | More (`…`) > Refresh | Refresh the existing source. | The newly approved optional fields become available without replacing the connection. |
| 1.4 | Data > `Projects`, then `Clients` | More (`…`) > Refresh | Refresh both existing sources. | Canonical lookup sources remain connected. |
| 1.5 | Action > Power Automate | Add flow | Select existing `UWC-AcceptCapture-v1`. | The app has the named flow as a data source; no new flow is created from Studio. |
| 1.6 | Tree > `Form1` | Delete | Delete only the blank `Form1`. | The unused blank form disappears; `Form2` remains bound to `Work Log`. |

## 2. Initialise capture state

Select **App**, choose the **OnStart** property, replace its value with the
following, then choose **Run OnStart**:

```powerfx
Set(varSubmissionKey, Text(GUID()));
Set(varHours, 0.5);
Set(varOtherDuration, false);
Set(varOutcome, "completed");
Set(varMore, false);
Set(varSubmitting, false);
Set(varSaveMessage, Blank());
Set(varLastCaptureId, Blank());
Set(varLastWorkLogItemId, Blank());
Set(varAttemptSubmissionKey, Blank());
Set(varAttemptPayloadJson, Blank());
Set(varLastSubmissionKey, Blank());
Set(varLastPayloadJson, Blank());
Set(varSelectedProject, Blank());
Set(varSecureSite, false);
Set(varPhotoPolicy, "allowed");
Set(varEvidenceRequirement, "not_required");
Set(varSourceAppVersion, "uwc-v1-test-1.0.0");
Set(varSupersedesCaptureId, Blank());
Set(varCorrectionReason, Blank())
```

Expected result: a new retry-stable submission key exists, duration defaults to
30 minutes, outcome defaults to completed, and no entry has been submitted.

## 3. Make the form mobile-first

Apply these exact properties:

| Step | Select | Property | Exact value | Expected result |
|---:|---|---|---|---|
| 3.1 | `Screen1` | `Fill` | `ColorValue("#F7F8FA")` | Neutral mobile background. |
| 3.2 | `Form2` | `DefaultMode` | `FormMode.New` | Form remains create-only. |
| 3.3 | `Form2` | `DataSource` | `[@'Work Log']` | `Work Log` remains canonical. |
| 3.4 | `Form2` | `Width` | `Parent.Width` | Form fills the phone width. |
| 3.5 | `Form2` | `Height` | `Parent.Height` | Form uses the available phone height and scrolls. |
| 3.6 | `Form2` | `X` | `0` | No horizontal offset. |
| 3.7 | `Form2` | `Y` | `0` | Capture starts at the top. |
| 3.8 | `Form2` | `SnapToColumns` | `false` | One responsive vertical column can use full width. |
| 3.9 | `Form2` | `Columns` | `1` | One-column thumb-friendly layout. |

In **Form2 > Edit fields**, retain the existing cards and drag them into this
order: `Project Record`, `What did you do?`, `Hours`, `Work Type`, `Billable`,
`Rate Code`, `Work Date`, `Client Record`, `Task or Job Reference`. Do not add
invoice, invoice status, approval status, action lookup, legacy `Project`, or
legacy `Client`.

## 4. Project and client controls

| Step | Select | Property | Exact value | Expected result |
|---:|---|---|---|---|
| 4.1 | `Project Record_DataCard1` | `DisplayName` | `"Project"` | Primary first field is labelled Project. |
| 4.2 | `DataCardValue9` | `Items` | `SortByColumns(Choices([@'Work Log'].'ProjectLookup'), "Value", SortOrder.Ascending)` | Canonical Projects lookup is alphabetical. |
| 4.3 | `DataCardValue9` | `DisplayFields` | `["Value"]` | Project title is displayed. |
| 4.4 | `DataCardValue9` | `SearchFields` | `["Value"]` | Typing searches project titles. |
| 4.5 | `DataCardValue9` | `SelectMultiple` | `false` | Exactly one canonical project is selected. |
| 4.6 | `DataCardValue9` | `AccessibleLabel` | `"Project"` | Screen-reader label is explicit. |
| 4.7 | `DataCardValue9` | `OnChange` | Paste the formula below. | Project record, client, and conservative secure/photo policy are frozen in app state. |

```powerfx
Set(varSelectedProject, LookUp(Projects, ID = DataCardValue9.Selected.Id));
Set(
    varSecureSite,
    Coalesce(varSelectedProject.'Security Classification'.Value, "Standard") <> "Standard"
);
Set(varPhotoPolicy, If(varSecureSite, "prohibited", "allowed"));
Reset(DataCardValue8)
```

The non-`Standard` rule is deliberately conservative: the exported Projects
schema has `Security Classification` but no separate approved photo-policy
field. Any non-standard project therefore gets no-photo treatment. The
acceptance flow must repeat the policy check and remains authoritative.

Apply the client properties:

| Step | Select | Property | Exact value | Expected result |
|---:|---|---|---|---|
| 4.8 | `DataCardValue8` | `DefaultSelectedItems` | `Filter(Choices([@'Work Log'].'ClientLookup'), Id = varSelectedProject.'Client Record'.Id)` | Canonical Client lookup derives from the selected Project. |
| 4.9 | `DataCardValue8` | `DisplayMode` | `DisplayMode.View` | Client cannot be independently changed. |
| 4.10 | `Client Record_DataCard1` | `Visible` | `varMore And Not(IsBlank(varSelectedProject.'Client Record'.Id))` | Client is hidden in the fast path and shown read-only under More. |

## 5. Summary and date

| Step | Select | Property | Exact value | Expected result |
|---:|---|---|---|---|
| 5.1 | `DataCardKey8` | `Text` | `"What did you do?"` | Plain-language prompt. |
| 5.2 | `DataCardValue7` | `Mode` | `TextMode.MultiLine` | Field notes support multiple lines. |
| 5.3 | `DataCardValue7` | `Height` | `160` | Large thumb/dictation input. |
| 5.4 | `DataCardValue7` | `HintText` | `"Briefly describe the work completed"` | Short guidance appears when empty. |
| 5.5 | `DataCardValue7` | `AccessibleLabel` | `"What did you do?"` | Accessible field name. |
| 5.6 | `DateValue1` | `DefaultDate` | `Today()` | Work Date defaults to today. |
| 5.7 | `HourValue1` | `Visible` | `false` | Time-of-day is hidden in V1. |
| 5.8 | `Separator1` | `Visible` | `false` | Time separator is hidden. |
| 5.9 | `MinuteValue1` | `Visible` | `false` | Minutes-of-day are hidden. |
| 5.10 | `Work Date_DataCard1` | `Visible` | `varMore` | Today is applied automatically; date correction is under More. |

Do not change the `TechnicalSummary` data binding. The acceptance flow maps the
same human-confirmed text to new `WorkSummary` and existing
`TechnicalSummary`; this preserves compatibility without adding a second text
box.

## 6. Fix duration and add Other

Unlock `Hours_DataCard1` if Studio requires it. Apply these values to the four
existing buttons; this corrects the exported defect in which all four are 30m.

| Control | Property | Exact value |
|---|---|---|
| `Button1` | `Text` | `"15m"` |
| `Button1` | `OnSelect` | `Set(varHours, 0.25); Set(varOtherDuration, false); Reset(DataCardValue4)` |
| `Button1_1` | `Text` | `"30m"` |
| `Button1_1` | `OnSelect` | `Set(varHours, 0.5); Set(varOtherDuration, false); Reset(DataCardValue4)` |
| `Button1_2` | `Text` | `"1h"` |
| `Button1_2` | `OnSelect` | `Set(varHours, 1); Set(varOtherDuration, false); Reset(DataCardValue4)` |
| `Button1_3` | `Text` | `"2h"` |
| `Button1_3` | `OnSelect` | `Set(varHours, 2); Set(varOtherDuration, false); Reset(DataCardValue4)` |

Duplicate `Button1_3` once, rename the duplicate `uwcDurationOther`, and set:

| Property | Exact value |
|---|---|
| `Text` | `"Other"` |
| `OnSelect` | `Set(varOtherDuration, true); SetFocus(DataCardValue4)` |
| `AccessibleLabel` | `"Enter another duration"` |

Then set:

| Select | Property | Exact value | Expected result |
|---|---|---|---|
| `DataCardValue4` | `Default` | `Text(varHours, "0.##")` | Selected hours are visible for manual review. |
| `DataCardValue4` | `Visible` | `varOtherDuration` | Numeric input appears only after Other. |
| `DataCardValue4` | `OnChange` | `Set(varHours, Value(Self.Text))` | Manual hours update canonical minutes. |
| `DataCardValue4` | `AccessibleLabel` | `"Duration in hours"` | Manual entry is accessible. |
| `Hours_DataCard1` | `Update` | `varHours` | Existing `Hours` compatibility remains exact. |

Keep every duration button at least 48 px high. Expected result: 15m, 30m, 1h,
2h, and Other select `0.25`, `0.5`, `1`, `2`, or a positive manual hours value;
the flow submits `Round(varHours * 60, 0)` as canonical minutes.

## 7. Add Outcome and progressive fields

In **Form2 > Edit fields**, add only these approved fields: `Outcome Status`,
`Follow-up Required`, `Follow-up Summary`, `Follow-up Due`, and
`Evidence Requirement Applied`. Do not add any administrative or hidden
provenance fields to the form.

After Studio generates the cards, rename the card and its primary input exactly
as follows. The primary input is the Combo box, Toggle, Text input, or Date
picker inside the generated card.

| Field | Rename card to | Rename primary input to |
|---|---|---|
| Outcome Status | `uwcOutcomeCard` | `uwcOutcome` |
| Follow-up Required | `uwcFollowUpCard` | `uwcFollowUp` |
| Follow-up Summary | `uwcFollowUpSummaryCard` | `uwcFollowUpSummary` |
| Follow-up Due | `uwcFollowUpDueCard` | `uwcFollowUpDue` |
| Evidence Requirement Applied | `uwcEvidenceCard` | `uwcEvidenceRequirement` |

Set these exact properties:

| Select | Property | Exact value | Expected result |
|---|---|---|---|
| `uwcOutcome` | `Items` | `Choices([@'Work Log'].'OutcomeStatus')` | Uses the approved SharePoint choices. |
| `uwcOutcome` | `DefaultSelectedItems` | `Filter(Choices([@'Work Log'].'OutcomeStatus'), Value = varOutcome)` | Completed is the fast default. |
| `uwcOutcome` | `OnChange` | `Set(varOutcome, Self.Selected.Value)` | Explicit human outcome is captured. |
| `uwcOutcome` | `AccessibleLabel` | `"Outcome"` | Accessible outcome selector. |
| `uwcFollowUp` | `Default` | `false` | Follow-up is opt-in. |
| `uwcFollowUpSummaryCard` | `Visible` | `uwcFollowUp.Value` | Summary appears only after follow-up is selected. |
| `uwcFollowUpSummary` | `Mode` | `TextMode.MultiLine` | Follow-up can be concise but complete. |
| `uwcFollowUpSummary` | `HintText` | `"What needs to happen next?"` | No owner wording decision is needed. |
| `uwcFollowUpDueCard` | `Visible` | `uwcFollowUp.Value` | Due date is conditional. |
| `uwcFollowUpDue` | `DefaultDate` | `Today() + 1` | Safe next-day test default. |
| `uwcEvidenceRequirement` | `Items` | `Choices([@'Work Log'].'EvidenceRequirementApplied')` | Uses approved evidence choices. |
| `uwcEvidenceRequirement` | `DefaultSelectedItems` | `Filter(Choices([@'Work Log'].'EvidenceRequirementApplied'), Value = varEvidenceRequirement)` | Evidence starts not required. |
| `uwcEvidenceRequirement` | `OnChange` | `Set(varEvidenceRequirement, Self.Selected.Value)` | The human choice is frozen for submit. |
| `uwcEvidenceCard` | `Visible` | `varMore Or varSecureSite` | Evidence stays out of the normal path unless relevant. |

Drag the added cards so `uwcOutcomeCard` follows `Hours_DataCard1`, follow-up
cards follow billing, and `uwcEvidenceCard` follows the follow-up cards.

## 8. Work type, billing, Rate Code, task reference, and More

| Step | Select | Property | Exact value | Expected result |
|---:|---|---|---|---|
| 8.1 | `DataCardValue10` | `DefaultSelectedItems` | `If(IsBlank(Parent.Default), Filter(Choices([@'Work Log'].'WorkType'), Value = "Field Work"), Parent.Default)` | Existing Work Type choices and default are preserved. |
| 8.2 | `DataCardValue6` | `Default` | `false` | Synthetic test starts non-billable and cannot create a genuine invoice effect. |
| 8.2a | `DataCardValue6` | `DisplayMode` | `DisplayMode.Disabled` | The bounded synthetic activation cannot be made billable; later enablement requires separate finance approval. |
| 8.3 | `Rate Code_DataCard1` | `Visible` | `DataCardValue6.Value` | Existing Rate Code is shown only when billable is explicitly selected. |
| 8.4 | `DataCardValue5` | `Items` | `Choices([@'Work Log'].'RateCode')` | Existing values, including `APEX-95` and `Scheduled Night-135`, remain unchanged. |
| 8.5 | `Task or Job Reference_DataCard1` | `Visible` | `varMore` | Task/job reference is progressive. |
| 8.6 | `DataCardValue11` | `AccessibleLabel` | `"Task or job reference"` | The optional existing text field has an explicit accessible name. |

Select `Form2`, insert one **Custom card**, rename it `uwcMoreCard`; insert one
button inside it named `uwcMore`, then set:

| Select | Property | Exact value |
|---|---|---|
| `uwcMore` | `Text` | `If(varMore, "Hide optional fields", "More")` |
| `uwcMore` | `OnSelect` | `Set(varMore, Not(varMore))` |
| `uwcMore` | `AccessibleLabel` | `If(varMore, "Hide optional capture fields", "Show optional capture fields")` |

Drag `uwcMoreCard` immediately before `Work Date_DataCard1`. Expected result:
normal capture shows Project → What did you do? → Duration → Outcome → Work
Type → Billable → Follow-up → Submit. Date, client, task/reference, and optional
evidence remain behind More or a relevant condition.

## 9. Add the secure-site warning

Inside `uwcEvidenceCard`, insert a Label named `uwcPhotoWarning` and set:

| Property | Exact value |
|---|---|
| `Text` | `"SECURE SITE — photos are prohibited. Use an approved non-photo Project Files artifact."` |
| `Visible` | `varPhotoPolicy = "prohibited"` |
| `Color` | `ColorValue("#B42318")` |
| `FontWeight` | `FontWeight.Semibold` |
| `AutoHeight` | `true` |
| `Live` | `Live.Assertive` |

Do not add Camera, Add picture, Attachments, or file-content controls to this
capture form. Project Files is the binary destination, and an approved evidence
flow must reload policy and reject a prohibited photo before file creation.
This absence of a photo control plus server-side revalidation enforces the V1
secure-photo boundary.

## 10. Add status and the LOG WORK button

Select `Form2`, add one Custom card at the end, and rename it `uwcSubmitCard`.
Inside it insert a Label named `uwcSaveStatus` and a Modern button named
`uwcSubmit`.

Set the status label:

| Property | Exact value |
|---|---|
| `Text` | `varSaveMessage` |
| `Visible` | `Not(IsBlank(varSaveMessage))` |
| `Live` | `Live.Assertive` |
| `AutoHeight` | `true` |
| `Color` | `If(StartsWith(varSaveMessage, "Saved") Or StartsWith(varSaveMessage, "Already"), ColorValue("#107C10"), ColorValue("#B42318"))` |

Set the submit button:

| Property | Exact value |
|---|---|
| `Text` | `If(varSubmitting, "SAVING…", "LOG WORK")` |
| `Width` | `Parent.Width - 40` |
| `Height` | `64` |
| `X` | `20` |
| `AccessibleLabel` | `"Log work"` |
| `DisplayMode` | Paste the first formula below. |
| `OnSelect` | Paste the second formula below. |

`DisplayMode`:

```powerfx
If(
    varSubmitting
        Or IsBlank(DataCardValue9.Selected.Id)
        Or IsBlank(Trim(DataCardValue7.Text))
        Or varHours <= 0
        Or varHours > 24
        Or IsBlank(DataCardValue10.Selected.Value)
        Or IsBlank(uwcOutcome.Selected.Value)
        Or (uwcFollowUp.Value And IsBlank(Trim(uwcFollowUpSummary.Text))),
    DisplayMode.Disabled,
    DisplayMode.Edit
)
```

`OnSelect`:

```powerfx
Set(varSubmitting, true);
Set(varSaveMessage, Blank());
Set(varAttemptSubmissionKey, varSubmissionKey);
Set(
    varAttemptPayloadJson,
    JSON(
        {
            schemaVersion: "1.0.0",
            projectItemId: DataCardValue9.Selected.Id,
            clientItemId: DataCardValue8.Selected.Id,
            workDate: Text(DateValue1.SelectedDate, "yyyy-mm-dd"),
            durationMinutes: Round(varHours * 60, 0),
            workType: DataCardValue10.Selected.Value,
            workSummary: Trim(DataCardValue7.Text),
            outcomeStatus: uwcOutcome.Selected.Value,
            billingTreatment: "non_billable",
            rateCode: "",
            taskReference: If(varMore, Trim(DataCardValue11.Text), ""),
            followUpRequired: uwcFollowUp.Value,
            followUpSummary: If(uwcFollowUp.Value, Trim(uwcFollowUpSummary.Text), ""),
            followUpDue: If(uwcFollowUp.Value, Text(uwcFollowUpDue.SelectedDate, "yyyy-mm-dd"), ""),
            evidenceRequirement: uwcEvidenceRequirement.Selected.Value,
            secureSiteApplied: varSecureSite,
            photoPolicyApplied: varPhotoPolicy,
            captureMethod: "mobile_app",
            sourceAppVersion: varSourceAppVersion,
            projectProfileModified: varSelectedProject.Modified,
            factOrigin: "human_confirmed",
            supersedesCaptureId: Coalesce(varSupersedesCaptureId, ""),
            correctionReason: Coalesce(varCorrectionReason, "")
        },
        JSONFormat.Compact
    )
);
IfError(
    Set(
        varReceipt,
        'UWC-AcceptCapture-v1'.Run(
            varAttemptSubmissionKey,
            varAttemptPayloadJson
        )
    );
    If(
        Or(varReceipt.status = "saved", varReceipt.status = "already_saved"),
        Set(varLastCaptureId, varReceipt.captureId);
        Set(varLastWorkLogItemId, varReceipt.workLogItemId);
        Set(varLastSubmissionKey, varAttemptSubmissionKey);
        Set(varLastPayloadJson, varAttemptPayloadJson);
        Set(
            varSaveMessage,
            If(
                varReceipt.status = "already_saved",
                "Already saved — " & varReceipt.captureId,
                If(
                    varReceipt.evidenceStatus = "pending",
                    "Saved — evidence pending — " & varReceipt.captureId,
                    "Saved — " & varReceipt.captureId
                )
            )
        );
        Set(varSubmissionKey, Text(GUID()));
        Set(varHours, 0.5);
        Set(varOtherDuration, false);
        Set(varOutcome, "completed");
        Set(varMore, false);
        Set(varSelectedProject, Blank());
        Set(varSecureSite, false);
        Set(varPhotoPolicy, "allowed");
        Set(varEvidenceRequirement, "not_required");
        Set(varSupersedesCaptureId, Blank());
        Set(varCorrectionReason, Blank());
        ResetForm(Form2);
        NewForm(Form2),
        Set(
            varSaveMessage,
            If(
                varReceipt.status = "conflict",
                "Conflict — this submission key already has different facts. Entry retained.",
                "Not saved — " & Coalesce(varReceipt.message, "entry retained for retry")
            )
        )
    ),
    Set(varSaveMessage, "Not saved — " & FirstError.Message & ". Entry retained for retry.")
);
Set(varSubmitting, false)
```

Expected result: the app clears only after `saved` or `already_saved`; a flow
error, rejection, or conflict leaves the current entry and submission key in
place. A retry therefore reaches the idempotent flow with the same key.

## 11. Flow acceptance, App Checker, save, publish, and phone test

Perform these actions in order:

1. Preview with **Play** in Studio. Confirm Project search works; button labels
   are exactly 15m/30m/1h/2h/Other; non-standard Security Classification shows
   the no-photo warning; Billable is disabled and off; Rate Code remains hidden;
   follow-up detail appears only after Follow-up Required; More reveals
   date/client/task/evidence.
2. Use only a deterministic synthetic project/test profile. Keep Billable off.
   Enter summary `[SYNTHETIC UWC V1] manual-maker acceptance`, choose 15m,
   completed, no follow-up, no evidence, and press **LOG WORK** once. Expect
   `Saved — WC-…`, a reset form, and a new submission key.
3. In the flow's run history, select that successful run and **Resubmit** it.
   Require `status=already_saved` in `Respond_to_Power_Apps`, and verify that no
   second Work Log item exists for the submission key.
4. For conflict acceptance, insert one temporary Modern button
   on `Screen1`, rename it `uwcConflictTest`, and set its `Text` to
   `"TEST CONFLICT"`. Set `OnSelect` to the exact formula below, then select the
   temporary button. Require the green PASS notification and no second Work Log
   item. Delete `uwcConflictTest` immediately after the result.

   ```powerfx
   Set(
       varConflictReceipt,
       'UWC-AcceptCapture-v1'.Run(
           varLastSubmissionKey,
           Substitute(
               varLastPayloadJson,
               "[SYNTHETIC UWC V1] manual-maker acceptance",
               "[SYNTHETIC UWC V1] manual-maker acceptance changed"
           )
       )
   );
   If(
       varConflictReceipt.status = "conflict",
       Notify("PASS — changed facts rejected for the same key", NotificationType.Success),
       Notify("STOP — expected conflict; do not publish", NotificationType.Error)
   )
   ```

5. Repeat the remaining controlled acceptance cases through the app/flow:
   follow-up facts are retained only in Work Log; required evidence saves as
   pending; a non-Standard project has no photo control and policy mismatch is
   rejected; correction creates a higher revision with
   `SupersedesWorkCaptureID` and leaves the original unchanged. This pack does
   not create Actions or Project Files projections.
6. Select **App checker** after deleting `uwcConflictTest`. Resolve every formula
   error. Do not suppress a missing-field or missing-flow error. Resolve the
   accessibility warnings for the controls above before publishing.
7. Select **Save** on the existing app. Do not use **Save as**.
8. Select **Publish this version**. Confirm the app ID remains
   `a47efc3e-0b52-405a-a220-54930a4ffdc9`.
9. On Elliot's phone, open Power Apps, refresh the app list, and open this exact
   URL:

   `https://apps.powerapps.com/play/e/Default-aae6ab79-45eb-4829-a04f-595becdb936d/a/a47efc3e-0b52-405a-a220-54930a4ffdc9?tenantId=aae6ab79-45eb-4829-a04f-595becdb936d`

10. Keep Billable off. Enter summary `[SYNTHETIC UWC V1] mobile acceptance`,
    choose 15m, completed, no follow-up, no evidence, and press **LOG WORK**
    once. Expect `Saved — WC-…`, a reset form, and a new submission key.
11. Re-export the saved app through the same supported read-only app-document
   workflow, update the baseline hashes, review generated `.pa.yaml` only as a
   diff, validate, commit, and push. Never deploy the generated YAML.

Phone acceptance passes only when one canonical synthetic Work Log event exists
for one submission key, `Hours=0.25`, `DurationMinutes=15`, canonical Project and
Client lookups resolve, no invoice/approval fields changed, and no genuine or
customer data or evidence was used.
