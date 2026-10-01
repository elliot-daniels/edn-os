# Universal Work Capture V1 — supported manual-maker activation pack

Status: **Work Log 29-field schema is active; `UWC-AcceptCapture-v1` was not created. The 2026-08-21T20:05:00+09:30 to 2026-08-21T21:30:00+09:30 flow-creation window expired unused and is not reusable.**

This pack is bound to:

- manifest: `config/work-capture-v1-activation-manifest.json`
- required SHA-256:
  `ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca`
- SharePoint site: `https://edn123.sharepoint.com/sites/EDNSystems`
- Work Log ID: `7b6d10ec-c009-422a-9802-c907d3d4f57f`
- Power Apps environment: `EDN Systems (default)`
- existing app: `EDN Work Capture`
- app ID: `a47efc3e-0b52-405a-a220-54930a4ffdc9`

It uses only interactive PnP.PowerShell for the owner-run schema step and the
standard Power Apps and SharePoint connectors for the owner-built cloud flow.
It does not use Dataverse, a custom connector, an HTTP trigger, a premium
connector, deprecated PAC commands, generated YAML deployment, or a replacement
app.

## Contract decisions frozen by this pack

The minimum activation creates 29 approved optional Work Log fields. Five
proposal fields remain dormant because they are not needed by the exact V1
app/flow and their choice or commercial behavior is not frozen by the allowed
source documents:

- `WorkStartedAt`
- `RateClass`
- `BillingCode`
- `TechnicalValue`
- `TechnicalNote`

The pack does not guess those values or create partially specified columns.
Existing `RateCode`, `Hours`, finance fields, views, webhooks, Projects, Clients,
Actions, and legacy fields remain unchanged.

Choice values created by the bounded V1 script are exact and case-sensitive:

| Field | Values |
|---|---|
| `OutcomeStatus` | `completed`, `partial`, `blocked` |
| `BillingTreatment` | `billable`, `non_billable` |
| `EvidenceRequirementApplied` | `not_required`, `required` |
| `EvidenceStatus` | `not_required`, `pending`, `complete` |
| `PhotoPolicyApplied` | `allowed`, `prohibited`, `authorised` |
| `CaptureMethod` | `mobile_app` |
| `FactOrigin` | `human_confirmed` |

`WorkCaptureID` and `WorkCaptureSubmissionKey` are indexed and unique.
`DurationMinutes` and `WorkCapturePayloadHash` are indexed but not unique. All
new fields remain optional at SharePoint schema level.

### Standard-only payload integrity decision

The supported cloud-expression functions available to Power Automate do not
include SHA-256 or another cryptographic hash. Base64 is encoding, not hashing.
This pack therefore:

1. creates `WorkCapturePayloadHash` as the approved optional Text field;
2. leaves it blank in `UWC-AcceptCapture-v1` rather than storing a false hash;
3. compares every immutable accepted fact for duplicate/idempotency decisions;
4. treats same key/same facts as `already_saved` and same key/different facts as
   `conflict`; and
5. requires separate approval for any later cryptographic component.

This limitation does not weaken duplicate prevention: the unique submission-key
column and exact field comparison remain authoritative.

## A. Owner-run SharePoint schema script

Script:
`installer/Activate-UWCWorkLogSchema.ps1`

The script requires PowerShell 7.2 or later and an already installed
`PnP.PowerShell` module. It uses the existing interactive PnP client ID
`3c063b23-b83b-401b-9697-bf281c0d71b8` and does not create or change an Entra
application or permission.

From the repository root in PowerShell 7, first perform the non-mutating local
checks:

```powershell
(Get-FileHash .\config\work-capture-v1-activation-manifest.json -Algorithm SHA256).Hash.ToLowerInvariant()
Get-Module -ListAvailable PnP.PowerShell | Sort-Object Version -Descending | Select-Object -First 1 Name,Version
```

The first output must be exactly:

```text
ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca
```

If PnP.PowerShell is absent, stop. Do not install or consent to anything as an
implicit part of this pack.

Inside a separately approved activation window, the exact owner command is:

```powershell
pwsh.exe -NoLogo -NoProfile -File .\installer\Activate-UWCWorkLogSchema.ps1
```

The script performs one interactive sign-in, then:

1. re-hashes the manifest before authentication;
2. resolves the exact site and exact Work Log GUID;
3. preflights all current fields, canonical lookup targets, required existing
   field types, `Field Work`, `APEX-95`, and `Scheduled Night-135`;
4. fails before creation on an internal-name, field-ID, display-name, type,
   choice, requiredness, index, uniqueness, or lookup-target conflict;
5. snapshots every existing field schema, view, and webhook subscription;
6. creates only missing approved optional fields;
7. re-reads and validates all 29 fields; and
8. proves that every pre-existing field schema, view, and webhook subscription
   is unchanged.

Success ends with `Universal Work Capture V1 Work Log schema: PASS` and reports
created/reused fields plus zero existing-value, rate, finance, view, and webhook
mutations. A second run must report `Created (0)` and `Reused compatible (29)`.

Do not delete new optional fields during rollback. If the script stops after a
partial network failure, correct the connection problem and rerun the same
script; it reuses compatible fields and fails on conflicts.

## B. Manual maker runbook — `UWC-AcceptCapture-v1`

### B1. Create the instant flow

1. Open `https://make.powerautomate.com`.
2. Select environment **EDN Systems (default)**. Do not create a Dataverse
   database or solution.
3. Select **Create > Instant cloud flow**.
4. Flow name: `UWC-AcceptCapture-v1`.
5. Trigger: **Power Apps (V2)**.
6. Create the flow.
7. Open trigger **Settings**, enable **Concurrency control**, and set **Degree of
   parallelism** to `1`.
8. Add two trigger inputs in this exact order:

| Order | Name | Type |
|---:|---|---|
| 1 | `submissionKey` | Text |
| 2 | `payloadJson` | Text |

Do not add, rename, reorder, or change these inputs after the app is connected.

### B2. Fix the SharePoint connection boundary

Every SharePoint action below must use the existing connection to:

`https://edn123.sharepoint.com/sites/EDNSystems`

After saving the flow, open **Details > Run only users > Edit** and set the
SharePoint connection to **Provided by run-only user**. This makes the invoking
Elliot connection the SharePoint author. Do not use an owner-wide service
account, add permissions, or create a new connector.

### B3. Add response variables

Immediately after the trigger, add these **Initialize variable** actions in
order and rename each action to match the variable name:

| Variable | Type | Initial value/expression |
|---|---|---|
| `vSubmissionKey` | String | `toLower(trim(triggerBody()?['submissionKey']))` |
| `vStatus` | String | `rejected` |
| `vCaptureId` | String | `concat('WC-',toLower(trim(triggerBody()?['submissionKey'])))` |
| `vItemId` | String | leave empty |
| `vItemUrl` | String | leave empty |
| `vEvidenceStatus` | String | leave empty |
| `vMessage` | String | `Not saved` |
| `vRevision` | Integer | `1` |
| `vCanCreate` | Boolean | `false` |

Add a **Scope** named `TRY` after the variables. All actions in B4–B9 go inside
this scope.

For every value labelled **Expression** below, open the designer's Expression
tab and paste the shown function text exactly. The designer adds its internal
`@` marker; do not type an extra leading `@`.

### B4. Parse and validate the payload

Inside `TRY`, add **Data Operations > Parse JSON**, rename it `Parse_payload`,
set **Content** to:

```text
triggerBody()?['payloadJson']
```

Use this exact schema:

```json
{
  "type": "object",
  "properties": {
    "schemaVersion": { "type": "string" },
    "projectItemId": { "type": "integer" },
    "clientItemId": { "type": ["integer", "null"] },
    "workDate": { "type": "string" },
    "durationMinutes": { "type": "integer" },
    "workType": { "type": "string" },
    "workSummary": { "type": "string" },
    "outcomeStatus": { "type": "string" },
    "billingTreatment": { "type": "string" },
    "rateCode": { "type": "string" },
    "taskReference": { "type": "string" },
    "followUpRequired": { "type": "boolean" },
    "followUpSummary": { "type": "string" },
    "followUpDue": { "type": "string" },
    "evidenceRequirement": { "type": "string" },
    "secureSiteApplied": { "type": "boolean" },
    "photoPolicyApplied": { "type": "string" },
    "captureMethod": { "type": "string" },
    "sourceAppVersion": { "type": "string" },
    "projectProfileModified": { "type": "string" },
    "factOrigin": { "type": "string" },
    "supersedesCaptureId": { "type": "string" },
    "correctionReason": { "type": "string" }
  },
  "required": [
    "schemaVersion", "projectItemId", "clientItemId", "workDate", "durationMinutes",
    "workType", "workSummary", "outcomeStatus", "billingTreatment",
    "rateCode", "taskReference", "followUpRequired", "followUpSummary",
    "followUpDue", "evidenceRequirement", "secureSiteApplied",
    "photoPolicyApplied", "captureMethod", "sourceAppVersion",
    "projectProfileModified", "factOrigin",
    "supersedesCaptureId", "correctionReason"
  ]
}
```

Add a **Condition**, rename it `Payload_is_valid`, select **Expression**, and
paste:

```text
and(
  equals(length(variables('vSubmissionKey')),36),
  equals(length(replace(variables('vSubmissionKey'),'-','')),32),
  not(contains(variables('vSubmissionKey'),'''')),
  equals(body('Parse_payload')?['schemaVersion'],'1.0.0'),
  greaterOrEquals(int(body('Parse_payload')?['projectItemId']),1),
  greaterOrEquals(int(body('Parse_payload')?['durationMinutes']),1),
  lessOrEquals(int(body('Parse_payload')?['durationMinutes']),1440),
  greater(length(trim(body('Parse_payload')?['workSummary'])),0),
  lessOrEquals(length(trim(body('Parse_payload')?['workSummary'])),500),
  greater(length(trim(body('Parse_payload')?['workType'])),0),
  contains(createArray('completed','partial','blocked'),body('Parse_payload')?['outcomeStatus']),
  equals(body('Parse_payload')?['billingTreatment'],'non_billable'),
  empty(body('Parse_payload')?['rateCode']),
  lessOrEquals(length(body('Parse_payload')?['taskReference']),255),
  or(not(body('Parse_payload')?['followUpRequired']),greater(length(trim(body('Parse_payload')?['followUpSummary'])),0)),
  contains(createArray('not_required','required'),body('Parse_payload')?['evidenceRequirement']),
  contains(createArray('allowed','prohibited'),body('Parse_payload')?['photoPolicyApplied']),
  equals(body('Parse_payload')?['captureMethod'],'mobile_app'),
  equals(body('Parse_payload')?['sourceAppVersion'],'uwc-v1-test-1.0.0'),
  equals(body('Parse_payload')?['factOrigin'],'human_confirmed'),
  not(empty(body('Parse_payload')?['projectProfileModified'])),
  lessOrEquals(ticks(concat(body('Parse_payload')?['workDate'],'T00:00:00Z')),ticks(utcNow())),
  or(
    and(empty(body('Parse_payload')?['supersedesCaptureId']),empty(body('Parse_payload')?['correctionReason'])),
    and(not(empty(body('Parse_payload')?['supersedesCaptureId'])),greater(length(trim(body('Parse_payload')?['correctionReason'])),0))
  )
)
```

In the **If no** branch, add **Set variable** `vMessage`:

```text
Rejected — invalid or out-of-bound synthetic V1 payload
```

Put all remaining TRY actions in the **If yes** branch.

### B5. Find by submission key before any create

Add SharePoint **Get items**, rename it `Find_existing_capture`:

| Setting | Exact value |
|---|---|
| Site Address | `https://edn123.sharepoint.com/sites/EDNSystems` |
| List Name | `Work Log` |
| Filter Query | Expression below |
| Top Count | `2` |

Filter expression:

```text
concat('WorkCaptureSubmissionKey eq ''',variables('vSubmissionKey'),'''')
```

Add Condition `More_than_one_existing`:

```text
greater(length(body('Find_existing_capture')?['value']),1)
```

If yes, set:

- `vStatus` = `conflict`
- `vMessage` = `Conflict — duplicate submission-key data already exists`

In **If no**, add Condition `One_existing`:

```text
equals(length(body('Find_existing_capture')?['value']),1)
```

#### Existing-item branch

In `One_existing` **If yes**, add Condition `Exact_duplicate_facts` and paste:

```text
and(
  equals(string(first(body('Find_existing_capture')?['value'])?['WorkCaptureSchemaVersion']),body('Parse_payload')?['schemaVersion']),
  equals(string(first(body('Find_existing_capture')?['value'])?['WorkCaptureProjectID']),string(body('Parse_payload')?['projectItemId'])),
  equals(coalesce(string(first(body('Find_existing_capture')?['value'])?['WorkCaptureClientID']),''),if(empty(body('Parse_payload')?['clientItemId']),'',string(body('Parse_payload')?['clientItemId']))),
  equals(formatDateTime(first(body('Find_existing_capture')?['value'])?['WorkDate'],'yyyy-MM-dd'),body('Parse_payload')?['workDate']),
  equals(int(first(body('Find_existing_capture')?['value'])?['DurationMinutes']),int(body('Parse_payload')?['durationMinutes'])),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['WorkType/Value'],first(body('Find_existing_capture')?['value'])?['WorkType'])),body('Parse_payload')?['workType']),
  equals(string(first(body('Find_existing_capture')?['value'])?['WorkSummary']),trim(body('Parse_payload')?['workSummary'])),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['OutcomeStatus/Value'],first(body('Find_existing_capture')?['value'])?['OutcomeStatus'])),body('Parse_payload')?['outcomeStatus']),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['BillingTreatment/Value'],first(body('Find_existing_capture')?['value'])?['BillingTreatment'])),'non_billable'),
  equals(coalesce(string(first(body('Find_existing_capture')?['value'])?['TaskReference']),''),body('Parse_payload')?['taskReference']),
  equals(bool(first(body('Find_existing_capture')?['value'])?['FollowUpRequired']),bool(body('Parse_payload')?['followUpRequired'])),
  equals(coalesce(string(first(body('Find_existing_capture')?['value'])?['FollowUpSummary']),''),if(body('Parse_payload')?['followUpRequired'],trim(body('Parse_payload')?['followUpSummary']),'')),
  equals(if(empty(first(body('Find_existing_capture')?['value'])?['FollowUpDue']),'',formatDateTime(first(body('Find_existing_capture')?['value'])?['FollowUpDue'],'yyyy-MM-dd')),if(empty(body('Parse_payload')?['followUpDue']),'',body('Parse_payload')?['followUpDue'])),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['EvidenceRequirementApplied/Value'],first(body('Find_existing_capture')?['value'])?['EvidenceRequirementApplied'])),body('Parse_payload')?['evidenceRequirement']),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['EvidenceStatus/Value'],first(body('Find_existing_capture')?['value'])?['EvidenceStatus'])),if(equals(body('Parse_payload')?['evidenceRequirement'],'required'),'pending','not_required')),
  equals(bool(first(body('Find_existing_capture')?['value'])?['SecureSiteApplied']),bool(body('Parse_payload')?['secureSiteApplied'])),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['PhotoPolicyApplied/Value'],first(body('Find_existing_capture')?['value'])?['PhotoPolicyApplied'])),body('Parse_payload')?['photoPolicyApplied']),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['CaptureMethod/Value'],first(body('Find_existing_capture')?['value'])?['CaptureMethod'])),body('Parse_payload')?['captureMethod']),
  equals(string(first(body('Find_existing_capture')?['value'])?['SourceAppVersion']),body('Parse_payload')?['sourceAppVersion']),
  equals(string(first(body('Find_existing_capture')?['value'])?['ProjectProfileVersion']),concat('Projects:',string(body('Parse_payload')?['projectItemId']),':',formatDateTime(body('Parse_payload')?['projectProfileModified'],'yyyyMMddHHmmss'))),
  equals(string(coalesce(first(body('Find_existing_capture')?['value'])?['FactOrigin/Value'],first(body('Find_existing_capture')?['value'])?['FactOrigin'])),body('Parse_payload')?['factOrigin']),
  equals(coalesce(string(first(body('Find_existing_capture')?['value'])?['SupersedesWorkCaptureID']),''),body('Parse_payload')?['supersedesCaptureId']),
  equals(coalesce(string(first(body('Find_existing_capture')?['value'])?['CorrectionReason']),''),trim(body('Parse_payload')?['correctionReason']))
)
```

If `Exact_duplicate_facts` is **no**, set `vStatus=conflict` and
`vMessage=Conflict — this submission key already has different facts`.

If yes, add Condition `Existing_engineer_missing`:

```text
empty(first(body('Find_existing_capture')?['value'])?['Engineer/Claims'])
```

In its **If yes** branch, add SharePoint **Update item** named
`Repair_existing_engineer`. Map only:

- Site Address: exact EDN Systems site
- List Name: `Work Log`
- ID: existing item `ID`
- Title: existing item `Title`
- Engineer Claims: existing item dynamic content **Created By Claims**

Leave **If no** empty. After this condition, set:

| Variable | Exact value/expression |
|---|---|
| `vStatus` | `already_saved` |
| `vCaptureId` | `string(first(body('Find_existing_capture')?['value'])?['WorkCaptureID'])` |
| `vItemId` | `string(first(body('Find_existing_capture')?['value'])?['ID'])` |
| `vItemUrl` | `concat('https://edn123.sharepoint.com/sites/EDNSystems/Lists/Work%20Log/DispForm.aspx?ID=',variables('vItemId'))` |
| `vEvidenceStatus` | `string(coalesce(first(body('Find_existing_capture')?['value'])?['EvidenceStatus/Value'],first(body('Find_existing_capture')?['value'])?['EvidenceStatus']))` |
| `vMessage` | `Already saved` |

Both condition branches now converge on the same idempotent response.

#### New-item branch

Put B6–B8 in `One_existing` **If no**.

### B6. Revalidate the Project and applied policy

Add SharePoint **Get item**, rename it `Get_project`:

| Setting | Exact value |
|---|---|
| Site Address | exact EDN Systems site |
| List Name | `Projects` |
| Id | `int(body('Parse_payload')?['projectItemId'])` |

Add four **Compose** actions:

| Action name | Expression |
|---|---|
| `Derived_client_id` | `int(coalesce(outputs('Get_project')?['body/ClientLookup/Id'],outputs('Get_project')?['body/ClientLookupId'],0))` |
| `Derived_secure_site` | `not(equals(coalesce(outputs('Get_project')?['body/SecurityClassification/Value'],outputs('Get_project')?['body/SecurityClassification'],'Standard'),'Standard'))` |
| `Derived_photo_policy` | `if(outputs('Derived_secure_site'),'prohibited','allowed')` |
| `Derived_profile_version` | `concat('Projects:',string(body('Parse_payload')?['projectItemId']),':',formatDateTime(outputs('Get_project')?['body/Modified'],'yyyyMMddHHmmss'))` |

Add Condition `Project_policy_matches`:

```text
and(
  equals(int(coalesce(body('Parse_payload')?['clientItemId'],0)),outputs('Derived_client_id')),
  equals(bool(body('Parse_payload')?['secureSiteApplied']),outputs('Derived_secure_site')),
  equals(body('Parse_payload')?['photoPolicyApplied'],outputs('Derived_photo_policy')),
  equals(ticks(body('Parse_payload')?['projectProfileModified']),ticks(outputs('Get_project')?['body/Modified']))
)
```

If no, set `vMessage` to:

```text
Rejected — project, client, or secure/photo policy changed; refresh the entry
```

Put the remaining actions in **If yes**.

### B7. Resolve append-only correction lineage

Add Condition `Is_correction`:

```text
not(empty(body('Parse_payload')?['supersedesCaptureId']))
```

If no, set `vRevision=1` and `vCanCreate=true`.

If yes, add SharePoint **Get items** named `Find_superseded_capture`:

| Setting | Exact value |
|---|---|
| Site Address | exact EDN Systems site |
| List Name | `Work Log` |
| Filter Query | `concat('WorkCaptureID eq ''',replace(body('Parse_payload')?['supersedesCaptureId'],'''',''''''),'''')` |
| Top Count | `2` |

Add Condition `One_valid_superseded_capture`:

```text
and(
  equals(length(body('Find_superseded_capture')?['value']),1),
  equals(string(first(body('Find_superseded_capture')?['value'])?['WorkCaptureProjectID']),string(body('Parse_payload')?['projectItemId']))
)
```

If no, set `vMessage=Rejected — superseded capture is missing, ambiguous, or
belongs to another project`.

If yes:

- set `vRevision` to
  `add(int(first(body('Find_superseded_capture')?['value'])?['WorkCaptureRevision']),1)`;
- set `vCanCreate` to `true`.

Continue after `Is_correction` with Condition `Create_is_authorised`:

```text
equals(variables('vCanCreate'),true)
```

If no, perform no SharePoint write. Put B8 in **If yes**.

### B8. Create exactly one canonical Work Log item

Add SharePoint **Create item**, rename it `Create_work_log`. Use the exact EDN
Systems site and `Work Log` list. Refresh the action after the schema script so
all columns appear, then map:

| Work Log field | Exact value/expression |
|---|---|
| Title | `concat('[SYNTHETIC UWC V1] ',variables('vCaptureId'))` |
| Work Date | `body('Parse_payload')?['workDate']` |
| Project Record Id | `int(body('Parse_payload')?['projectItemId'])` |
| Client Record Id | `if(equals(outputs('Derived_client_id'),0),null,outputs('Derived_client_id'))` |
| Project | dynamic content **Title** from `Get_project` |
| Client | dynamic content **Client Record Value** from `Get_project`; blank if none |
| Task or Job Reference | `body('Parse_payload')?['taskReference']` |
| Work Type Value | `body('Parse_payload')?['workType']` |
| Hours | `div(float(body('Parse_payload')?['durationMinutes']),60)` |
| Billable | `false` |
| Technical Summary | `trim(body('Parse_payload')?['workSummary'])` |
| Work Capture ID | `variables('vCaptureId')` |
| Work Capture Submission Key | `variables('vSubmissionKey')` |
| Work Capture Schema Version | `1.0.0` |
| Work Capture Project ID | `string(body('Parse_payload')?['projectItemId'])` |
| Work Capture Client ID | `if(equals(outputs('Derived_client_id'),0),'',string(outputs('Derived_client_id')))` |
| Engineer | leave blank; B9 derives it from SharePoint Created By |
| Duration Minutes | `int(body('Parse_payload')?['durationMinutes'])` |
| Work Summary | `trim(body('Parse_payload')?['workSummary'])` |
| Outcome Status Value | `body('Parse_payload')?['outcomeStatus']` |
| Billing Treatment Value | `non_billable` |
| Follow-up Required | `body('Parse_payload')?['followUpRequired']` |
| Follow-up Summary | `if(body('Parse_payload')?['followUpRequired'],trim(body('Parse_payload')?['followUpSummary']),'')` |
| Follow-up Due | `if(empty(body('Parse_payload')?['followUpDue']),null,body('Parse_payload')?['followUpDue'])` |
| Evidence Requirement Applied Value | `body('Parse_payload')?['evidenceRequirement']` |
| Evidence Status Value | `if(equals(body('Parse_payload')?['evidenceRequirement'],'required'),'pending','not_required')` |
| Evidence References JSON | leave blank |
| Secure Site Applied | `outputs('Derived_secure_site')` |
| Photo Policy Applied Value | `outputs('Derived_photo_policy')` |
| Photo Authorization Ref | leave blank |
| Capture Method Value | `mobile_app` |
| Source App Version | `uwc-v1-test-1.0.0` |
| Captured At | `utcNow()` |
| Project Profile Version | `outputs('Derived_profile_version')` |
| Fact Origin Value | `human_confirmed` |
| Defaulted Fields JSON | `["clientItemId","captureMethod","capturedAt","factOrigin"]` |
| Work Capture Revision | `variables('vRevision')` |
| Supersedes Work Capture ID | `body('Parse_payload')?['supersedesCaptureId']` |
| Correction Reason | `trim(body('Parse_payload')?['correctionReason'])` |
| Work Capture Payload Hash | leave blank; field comparison is authoritative |

Do not expose or map Rate Code while Billable is false. Do not map invoice,
approval, invoice number, action lookup, Evidence & Test Results, attachments,
or any field not listed above.

### B9. Bind Engineer to the invoking SharePoint author and set the receipt

Add SharePoint **Get item**, rename it `Get_created_work_log`:

- Site Address: exact EDN Systems site
- List Name: `Work Log`
- Id: dynamic content **ID** from `Create_work_log`

Add SharePoint **Update item**, rename it `Set_engineer_from_author`:

- Site Address: exact EDN Systems site
- List Name: `Work Log`
- ID: dynamic content **ID** from `Get_created_work_log`
- Title: dynamic content **Title** from `Get_created_work_log`
- Engineer Claims: dynamic content **Created By Claims** from
  `Get_created_work_log`

Do not populate any other optional Update item field.

Then set variables:

| Variable | Exact value/expression |
|---|---|
| `vStatus` | `saved` |
| `vItemId` | `string(outputs('Create_work_log')?['body/ID'])` |
| `vItemUrl` | `concat('https://edn123.sharepoint.com/sites/EDNSystems/Lists/Work%20Log/DispForm.aspx?ID=',variables('vItemId'))` |
| `vEvidenceStatus` | `if(equals(body('Parse_payload')?['evidenceRequirement'],'required'),'pending','not_required')` |
| `vMessage` | `Saved` |

No Action item or Project Files file is created by this acceptance flow.
Follow-up facts remain canonical in Work Log; Actions projection and binary
evidence are separate optional flows outside this pack.

### B10. Add the error path and one response

After `TRY`, add a Scope named `CATCH`. Configure **Run after** so `CATCH` runs
only when `TRY` **has failed** or **has timed out**. Inside `CATCH`, set:

- `vStatus` = `rejected`
- `vCaptureId` = empty
- `vItemId` = empty
- `vItemUrl` = empty
- `vEvidenceStatus` = empty
- `vMessage` = expression:

```text
concat('Not saved — flow error; correlation ',workflow()?['run']?['name'])
```

After `CATCH`, add **Respond to a PowerApp or flow** named
`Respond_to_Power_Apps`. Configure its run-after to accept `CATCH` **is
successful** or **is skipped**. Add six Text outputs in this exact order:

| Output | Value |
|---|---|
| `status` | `variables('vStatus')` |
| `captureId` | `variables('vCaptureId')` |
| `workLogItemId` | `variables('vItemId')` |
| `workLogItemUrl` | `variables('vItemUrl')` |
| `evidenceStatus` | `variables('vEvidenceStatus')` |
| `message` | `variables('vMessage')` |

Run **Flow checker**, fix every error, and save. Do not turn the flow on for
other users, share it, or connect it to another app.

### B11. Synthetic flow acceptance

A Power Apps (V2) trigger cannot receive an owner-entered portal payload before
it has a Power Apps caller. Therefore the supported order is: Flow checker and
save first; attach the flow to the existing app; then perform the runtime tests.
Do not create a replacement test app or change the trigger just to run it.

After the flow is attached through the Studio runbook:

1. Keep Billable false and use only a deterministic synthetic project.
2. Submit `[SYNTHETIC UWC V1] manual-maker acceptance`, 15 minutes, completed,
   no follow-up, no evidence. Expect `status=saved`, one Work Log item,
   `Hours=0.25`, `DurationMinutes=15`, correct canonical lookup IDs,
   Engineer=Created By, and no finance fields.
3. In Power Automate, use **Test > Automatically > With data from a previous
   run** on that successful run. Expect `already_saved` and the same item ID;
   verify the submission-key filter returns one item.
4. For conflict testing, before publish use the exact temporary Studio test
   procedure in the reconciled Studio runbook. Expect `conflict` and no second
   item, then delete the temporary test control.
5. Submit a second synthetic entry with Follow-up Required and a non-empty
   summary. Verify only Work Log follow-up fields; no Action is expected.
6. Submit `evidenceRequirement=required`; expect the capture to save with
   `EvidenceStatus=pending` and no file.
7. Use a non-Standard synthetic project; expect `SecureSiteApplied=true`,
   `PhotoPolicyApplied=prohibited`, no photo control, and flow rejection if the
   app-supplied policy does not match the project.
8. Submit a correction using the prior `WorkCaptureID` and a correction reason;
   expect a new capture, revision +1, and the original unchanged.

## C. Power Apps Studio reconciliation

`docs/work-capture/POWER-APPS-STUDIO-V1-RUNBOOK.md` is reconciled to this exact
flow contract. The material corrections are:

1. `CaptureMethod` is `mobile_app`, matching the approved SharePoint choice.
2. The payload sends `projectProfileModified` as the selected Projects
   `Modified` value; the flow derives and verifies `ProjectProfileVersion`.
3. The activation build keeps Billable disabled/false; the flow rejects any
   billable payload, preventing finance effects.
4. The submit formula computes `varAttemptPayloadJson` once and uses exactly the
   two flow inputs `submissionKey` and `payloadJson`.
5. The six response names remain exactly `status`, `captureId`,
   `workLogItemId`, `workLogItemUrl`, `evidenceStatus`, and `message`.
6. Follow-up acceptance verifies Work Log facts only; it does not claim an
   Actions projection.
7. The temporary conflict-test control is deleted before App Checker/publish.

No generated `.pa.yaml` is edited and the live app remains unchanged until the
owner performs that runbook.

## D. Exact owner execution order

1. Obtain a fresh owner-approved synthetic activation window bound to the exact
   manifest hash above.
2. From the repository root in PowerShell 7, run:
   `pwsh.exe -NoLogo -NoProfile -File .\installer\Activate-UWCWorkLogSchema.ps1`.
3. Require the script's `PASS`; rerun it once and require `Created (0)` and
   `Reused compatible (29)`.
4. In Power Automate, create `UWC-AcceptCapture-v1` exactly as section B, run
   Flow checker, save it, and configure SharePoint as **Provided by run-only
   user**. This is the only supported pre-caller test available.
5. Open only existing app `EDN Work Capture`
   (`a47efc3e-0b52-405a-a220-54930a4ffdc9`) in Studio, refresh Work Log, and
   attach the exact flow. This attachment is required before any runtime test of
   a Power Apps (V2) trigger.
6. Perform B11's first synthetic saved/retry test. Stop on any non-synthetic
   data, permission prompt beyond the existing SharePoint connection, duplicate,
   finance-field effect, field mismatch, or policy drift.
7. Execute the complete reconciled Studio runbook, including the temporary
   conflict test, then delete the temporary test control.
8. Run App Checker and resolve every formula/accessibility error.
9. Save the existing app; do not use Save as. Publish this version and confirm
   the app ID is unchanged.
10. On Elliot's phone, open:

    `https://apps.powerapps.com/play/e/Default-aae6ab79-45eb-4829-a04f-595becdb936d/a/a47efc3e-0b52-405a-a220-54930a4ffdc9?tenantId=aae6ab79-45eb-4829-a04f-595becdb936d`

11. Perform the first synthetic phone capture: deterministic synthetic project,
    summary `[SYNTHETIC UWC V1] first phone capture`, 15m, completed, Billable
    false, no follow-up, no evidence. Require one canonical item and a visible
    `Saved — WC-…` receipt followed by reset.

The requested portal-runtime test cannot precede attaching a Power Apps (V2)
flow to a caller. Steps 4–6 preserve the requested intent without inventing an
unsupported portal runner or replacement app.
