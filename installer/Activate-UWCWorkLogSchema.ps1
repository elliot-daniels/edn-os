#Requires -Version 7.2
#Requires -Modules PnP.PowerShell

<#
.SYNOPSIS
Applies the bounded Universal Work Capture V1 additive Work Log schema.

.DESCRIPTION
This script is deliberately interactive and idempotent. It verifies the exact
manifest hash, site, list, canonical existing bindings, every bounded field,
views, and webhook subscriptions before creating any missing field. It never
deletes, renames, changes an existing field, reads list items, or changes views,
webhooks, permissions, finance fields, commercial choices, or existing values.

Run only inside an owner-approved activation window. Repository validation must
parse and inspect this file but must not execute it.
#>

[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$siteUrl = "https://edn123.sharepoint.com/sites/EDNSystems"
$workLogId = [Guid]"7b6d10ec-c009-422a-9802-c907d3d4f57f"
$projectsId = [Guid]"66944251-b9a3-40cc-9a59-05538e200c19"
$clientsId = [Guid]"3d55c612-9799-4462-9474-7f0ca5a10b24"
$actionsId = [Guid]"d7079aad-7f18-4164-8bd6-41f5629898bb"
$clientId = "3c063b23-b83b-401b-9697-bf281c0d71b8"
$requiredManifestHash = "ce24ad151a868f2f31a46849935201d9413dd93d600deb9348089ba4e474edca"
$manifestPath = Join-Path $PSScriptRoot "..\config\work-capture-v1-activation-manifest.json"
$fieldGroup = "EDN Universal Work Capture V1"

function Stop-Activation {
    param([Parameter(Mandatory)][string]$Message)

    throw "UWC schema activation stopped: $Message"
}

function Get-LowerSha256 {
    param([Parameter(Mandatory)][string]$Text)

    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    return [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData($bytes)
    ).ToLowerInvariant()
}

function Get-NormalizedGuidText {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return ""
    }
    return ([string]$Value).Trim("{} ").ToLowerInvariant()
}

function Test-EquivalentSharePointSiteUrl {
    param(
        [Parameter(Mandatory)][string]$ExpectedUrl,
        [Parameter(Mandatory)][string]$ActualUrl
    )

    $identities = foreach ($candidate in @($ExpectedUrl, $ActualUrl)) {
        $parsed = $null
        if (-not [Uri]::TryCreate(
            $candidate,
            [UriKind]::Absolute,
            [ref]$parsed
        )) {
            throw "Invalid absolute SharePoint site URL '$candidate'."
        }
        if (
            -not [StringComparer]::OrdinalIgnoreCase.Equals(
                $parsed.Scheme,
                [Uri]::UriSchemeHttps
            ) -or
            -not $parsed.IsDefaultPort -or
            -not [string]::IsNullOrEmpty($parsed.UserInfo) -or
            -not [string]::IsNullOrEmpty($parsed.Query) -or
            -not [string]::IsNullOrEmpty($parsed.Fragment)
        ) {
            throw "Unsafe SharePoint site URL '$candidate'."
        }

        $path = $parsed.AbsolutePath.TrimEnd("/")
        if ([string]::IsNullOrEmpty($path)) {
            $path = "/"
        }
        [pscustomobject]@{
            Host = $parsed.IdnHost
            Path = $path
        }
    }

    return (
        [StringComparer]::OrdinalIgnoreCase.Equals(
            $identities[0].Host,
            $identities[1].Host
        ) -and
        [StringComparer]::OrdinalIgnoreCase.Equals(
            $identities[0].Path,
            $identities[1].Path
        )
    )
}

function Get-UwcFieldSchemaDocument {
    param([Parameter(Mandatory)][object]$Field)

    if ([string]::IsNullOrWhiteSpace([string]$Field.SchemaXml)) {
        throw "Field '$($Field.InternalName)' has no loaded SchemaXml."
    }
    try {
        $document = [xml]$Field.SchemaXml
    }
    catch {
        throw "Field '$($Field.InternalName)' has invalid SchemaXml: $($_.Exception.Message)"
    }
    if ($null -eq $document.DocumentElement -or $document.DocumentElement.LocalName -cne "Field") {
        throw "Field '$($Field.InternalName)' SchemaXml has no Field root."
    }
    return $document
}

function Get-UwcChoiceValuesFromSchema {
    param([Parameter(Mandatory)][object]$Field)

    $document = Get-UwcFieldSchemaDocument $Field
    if ($document.DocumentElement.GetAttribute("Type") -cne "Choice") {
        throw "Field '$($Field.InternalName)' SchemaXml is not Type Choice."
    }
    $choiceNodes = @(
        $document.DocumentElement.SelectNodes(
            "./*[local-name()='CHOICES']/*[local-name()='CHOICE']"
        )
    )
    if ($choiceNodes.Count -eq 0) {
        throw "Choice field '$($Field.InternalName)' exposes no CHOICE values in SchemaXml."
    }
    return [string[]]@($choiceNodes | ForEach-Object { $_.InnerText })
}

function Get-UwcLookupIdentityFromSchema {
    param([Parameter(Mandatory)][object]$Field)

    $document = Get-UwcFieldSchemaDocument $Field
    if ($document.DocumentElement.GetAttribute("Type") -cne "Lookup") {
        throw "Field '$($Field.InternalName)' SchemaXml is not Type Lookup."
    }
    $lookupList = $document.DocumentElement.GetAttribute("List")
    $lookupField = $document.DocumentElement.GetAttribute("ShowField")
    if (
        [string]::IsNullOrWhiteSpace($lookupList) -or
        [string]::IsNullOrWhiteSpace($lookupField)
    ) {
        throw "Lookup field '$($Field.InternalName)' has incomplete SchemaXml identity."
    }
    return [pscustomobject]@{
        List = $lookupList
        Field = $lookupField
    }
}

function New-UwcFieldXml {
    param([Parameter(Mandatory)][pscustomobject]$Definition)

    $document = [Xml.XmlDocument]::new()
    $field = $document.CreateElement("Field")
    $field.SetAttribute("Type", $Definition.Type)
    $field.SetAttribute("Name", $Definition.InternalName)
    $field.SetAttribute("StaticName", $Definition.InternalName)
    $field.SetAttribute("DisplayName", $Definition.DisplayName)
    $field.SetAttribute("ID", "{$($Definition.Id)}")
    $field.SetAttribute("Group", $fieldGroup)
    $field.SetAttribute("Required", "FALSE")
    $field.SetAttribute("Hidden", "FALSE")
    $field.SetAttribute("ReadOnly", "FALSE")
    $field.SetAttribute("Indexed", $Definition.Indexed.ToString().ToUpperInvariant())
    $field.SetAttribute(
        "EnforceUniqueValues",
        $Definition.Unique.ToString().ToUpperInvariant()
    )

    switch ($Definition.Type) {
        "Text" {
            $field.SetAttribute("MaxLength", "255")
        }
        "Note" {
            $field.SetAttribute("NumLines", "6")
            $field.SetAttribute("RichText", "FALSE")
            $field.SetAttribute("AppendOnly", "FALSE")
        }
        "User" {
            $field.SetAttribute("UserSelectionMode", "PeopleOnly")
            $field.SetAttribute("UserSelectionScope", "0")
        }
        "DateTime" {
            $field.SetAttribute("Format", "DateTime")
            $field.SetAttribute("FriendlyDisplayFormat", "Disabled")
        }
        "Number" {
            $field.SetAttribute("Decimals", "0")
            $field.SetAttribute("Percentage", "FALSE")
        }
        "Choice" {
            $field.SetAttribute("Format", "Dropdown")
            $field.SetAttribute("FillInChoice", "FALSE")
            $choices = $document.CreateElement("CHOICES")
            foreach ($choiceValue in $Definition.Choices) {
                $choice = $document.CreateElement("CHOICE")
                $choice.InnerText = $choiceValue
                [void]$choices.AppendChild($choice)
            }
            [void]$field.AppendChild($choices)
        }
    }

    if ($null -ne $Definition.DefaultValue) {
        $default = $document.CreateElement("Default")
        $default.InnerText = [string]$Definition.DefaultValue
        [void]$field.AppendChild($default)
    }

    return $field.OuterXml
}

function Assert-NewFieldCompatible {
    param(
        [Parameter(Mandatory)][object]$Field,
        [Parameter(Mandatory)][pscustomobject]$Definition
    )

    if ($Field.InternalName -cne $Definition.InternalName) {
        Stop-Activation "Internal-name conflict for $($Definition.InternalName)."
    }
    if ($Field.Title -cne $Definition.DisplayName) {
        Stop-Activation (
            "Display-name conflict for $($Definition.InternalName): " +
            "expected '$($Definition.DisplayName)', found '$($Field.Title)'."
        )
    }
    if ($Field.TypeAsString -cne $Definition.Type) {
        Stop-Activation (
            "Type conflict for $($Definition.InternalName): " +
            "expected $($Definition.Type), found $($Field.TypeAsString)."
        )
    }
    if ($Field.Required -or $Field.ReadOnlyField) {
        Stop-Activation (
            "$($Definition.InternalName) exists but is required or read-only; " +
            "the approved field must be optional and writable."
        )
    }
    if ($Definition.Type -eq "Choice") {
        $expectedChoices = @($Definition.Choices | Sort-Object)
        $actualChoices = @(Get-UwcChoiceValuesFromSchema $Field | Sort-Object)
        if (($expectedChoices -join "`n") -cne ($actualChoices -join "`n")) {
            Stop-Activation (
                "Choice conflict for $($Definition.InternalName): expected " +
                "[$($expectedChoices -join ', ')], found " +
                "[$($actualChoices -join ', ')]."
            )
        }
    }
    if ($Definition.Indexed -and -not $Field.Indexed) {
        Stop-Activation "$($Definition.InternalName) exists but is not indexed."
    }
    if ($Field.EnforceUniqueValues -ne $Definition.Unique) {
        Stop-Activation (
            "Uniqueness conflict for $($Definition.InternalName): expected " +
            "$($Definition.Unique), found $($Field.EnforceUniqueValues)."
        )
    }
}

function Assert-ExistingField {
    param(
        [Parameter(Mandatory)][hashtable]$FieldMap,
        [Parameter(Mandatory)][string]$InternalName,
        [Parameter(Mandatory)][string]$Type,
        [AllowNull()][Guid]$LookupList,
        [string[]]$RequiredChoices = @()
    )

    if (-not $FieldMap.ContainsKey($InternalName)) {
        Stop-Activation "Required existing field '$InternalName' is missing."
    }
    $field = $FieldMap[$InternalName]
    if ($field.TypeAsString -cne $Type) {
        Stop-Activation (
            "Existing field '$InternalName' has type $($field.TypeAsString); " +
            "expected $Type."
        )
    }
    if ($Type -eq "Lookup") {
        $lookupIdentity = Get-UwcLookupIdentityFromSchema $field
        $actualLookupList = Get-NormalizedGuidText $lookupIdentity.List
        if ($actualLookupList -cne $LookupList.ToString().ToLowerInvariant()) {
            Stop-Activation (
                "Existing lookup '$InternalName' targets $actualLookupList; " +
                "expected $LookupList."
            )
        }
        if ($lookupIdentity.Field -cne "Title") {
            Stop-Activation (
                "Existing lookup '$InternalName' targets '$($lookupIdentity.Field)'; " +
                "expected Title."
            )
        }
    }
    if ($RequiredChoices.Count -gt 0) {
        $actualChoices = @(Get-UwcChoiceValuesFromSchema $field)
        foreach ($choice in $RequiredChoices) {
            if ($actualChoices -cnotcontains $choice) {
                Stop-Activation (
                    "Existing choice field '$InternalName' is missing approved " +
                    "value '$choice'."
                )
            }
        }
    }
}

function Get-ExistingSchemaSnapshot {
    param(
        [Parameter(Mandatory)][object[]]$Fields,
        [Parameter(Mandatory)][Guid[]]$OriginalFieldIds,
        [Parameter(Mandatory)][object[]]$Views,
        [Parameter(Mandatory)][object[]]$Webhooks
    )

    $idSet = @{}
    foreach ($fieldId in $OriginalFieldIds) {
        $idSet[$fieldId.ToString().ToLowerInvariant()] = $true
    }

    $fieldSnapshot = @(
        $Fields |
            Where-Object {
                $idSet.ContainsKey($_.Id.ToString().ToLowerInvariant())
            } |
            Sort-Object InternalName |
            ForEach-Object {
                [ordered]@{
                    Id = $_.Id.ToString().ToLowerInvariant()
                    InternalName = $_.InternalName
                    SchemaXml = $_.SchemaXml
                }
            }
    )
    if ($fieldSnapshot.Count -ne $OriginalFieldIds.Count) {
        Stop-Activation "An existing field disappeared during activation."
    }

    $viewSnapshot = @(
        $Views |
            Sort-Object Id |
            ForEach-Object {
                [ordered]@{
                    Id = $_.Id.ToString().ToLowerInvariant()
                    Title = $_.Title
                    DefaultView = $_.DefaultView
                    RowLimit = $_.RowLimit
                    Paged = $_.Paged
                    ViewQuery = $_.ViewQuery
                    ViewFields = @($_.ViewFields)
                }
            }
    )
    $webhookSnapshot = @(
        $Webhooks |
            Sort-Object Id |
            ForEach-Object {
                [ordered]@{
                    Id = [string]$_.Id
                    NotificationUrl = [string]$_.NotificationUrl
                    ExpirationDateTime = [string]$_.ExpirationDateTime
                    ClientState = [string]$_.ClientState
                }
            }
    )

    $json = [ordered]@{
        Fields = $fieldSnapshot
        Views = $viewSnapshot
        Webhooks = $webhookSnapshot
    } | ConvertTo-Json -Depth 12 -Compress
    return [pscustomobject]@{
        Hash = Get-LowerSha256 $json
        FieldCount = $fieldSnapshot.Count
        ViewCount = $viewSnapshot.Count
        WebhookCount = $webhookSnapshot.Count
    }
}

$definitions = @(
    [pscustomobject]@{ DisplayName = "Work Capture ID"; InternalName = "WorkCaptureID"; Id = [Guid]"2cfc214c-adc6-5b3b-a5ec-35461edfa7a1"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $true; Unique = $true }
    [pscustomobject]@{ DisplayName = "Work Capture Submission Key"; InternalName = "WorkCaptureSubmissionKey"; Id = [Guid]"ce69fa01-eca6-5c72-9ace-320294ef35c8"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $true; Unique = $true }
    [pscustomobject]@{ DisplayName = "Work Capture Schema Version"; InternalName = "WorkCaptureSchemaVersion"; Id = [Guid]"3cebb239-ef60-5cde-b79c-e540e51f266f"; Type = "Text"; Choices = @(); DefaultValue = "1.0.0"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Work Capture Project ID"; InternalName = "WorkCaptureProjectID"; Id = [Guid]"07aa8de4-e8b9-529a-bfc4-b73c6912d484"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Work Capture Client ID"; InternalName = "WorkCaptureClientID"; Id = [Guid]"302cf34c-4edf-5c56-9f1e-3a349426d1fe"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Engineer"; InternalName = "Engineer"; Id = [Guid]"44feadad-bca4-5041-8070-d0136f07ab62"; Type = "User"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Duration Minutes"; InternalName = "DurationMinutes"; Id = [Guid]"74172404-3fc8-5210-b74c-d6be5aded334"; Type = "Number"; Choices = @(); DefaultValue = $null; Indexed = $true; Unique = $false }
    [pscustomobject]@{ DisplayName = "Work Summary"; InternalName = "WorkSummary"; Id = [Guid]"55915cbb-0c83-572c-89ce-3bec66ef5663"; Type = "Note"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Outcome Status"; InternalName = "OutcomeStatus"; Id = [Guid]"ed73ee87-abba-5f7e-b40b-e508e1350f27"; Type = "Choice"; Choices = @("completed", "partial", "blocked"); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Billing Treatment"; InternalName = "BillingTreatment"; Id = [Guid]"521cc36f-6cb5-5b34-a37b-8d3476eeb25f"; Type = "Choice"; Choices = @("billable", "non_billable"); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Follow-up Required"; InternalName = "FollowUpRequired"; Id = [Guid]"85aaed75-797f-5391-9325-f1307efc983e"; Type = "Boolean"; Choices = @(); DefaultValue = "0"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Follow-up Summary"; InternalName = "FollowUpSummary"; Id = [Guid]"3956ddbb-063c-5204-8083-9af7a8102001"; Type = "Note"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Follow-up Due"; InternalName = "FollowUpDue"; Id = [Guid]"cc062860-d737-539c-a2dd-be66cd0bb1d5"; Type = "DateTime"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Evidence Requirement Applied"; InternalName = "EvidenceRequirementApplied"; Id = [Guid]"b4f3252f-3c72-55b8-883b-6be73e19b6ff"; Type = "Choice"; Choices = @("not_required", "required"); DefaultValue = "not_required"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Evidence Status"; InternalName = "EvidenceStatus"; Id = [Guid]"4a72ebb2-223c-5514-abdd-f533995e38be"; Type = "Choice"; Choices = @("not_required", "pending", "complete"); DefaultValue = "not_required"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Evidence References JSON"; InternalName = "EvidenceReferencesJson"; Id = [Guid]"0270ec15-4465-54e4-be9f-85a3914a4af0"; Type = "Note"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Secure Site Applied"; InternalName = "SecureSiteApplied"; Id = [Guid]"e7ccac1f-3485-5518-a34b-37473923300f"; Type = "Boolean"; Choices = @(); DefaultValue = "0"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Photo Policy Applied"; InternalName = "PhotoPolicyApplied"; Id = [Guid]"e69e44ad-d76f-531a-bbc1-0c37c0093421"; Type = "Choice"; Choices = @("allowed", "prohibited", "authorised"); DefaultValue = "allowed"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Photo Authorization Ref"; InternalName = "PhotoAuthorizationRef"; Id = [Guid]"6c2251da-db8e-550e-86cc-eaf0a7c92889"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Capture Method"; InternalName = "CaptureMethod"; Id = [Guid]"335cff50-2e77-5967-9398-d343def0e5a4"; Type = "Choice"; Choices = @("mobile_app"); DefaultValue = "mobile_app"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Source App Version"; InternalName = "SourceAppVersion"; Id = [Guid]"c9ac4e11-5b22-5ae5-b241-5c3136ad1c33"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Captured At"; InternalName = "CapturedAt"; Id = [Guid]"a8a0e931-3b79-5d03-8e64-53ff3586e12b"; Type = "DateTime"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Project Profile Version"; InternalName = "ProjectProfileVersion"; Id = [Guid]"10f91919-894e-558e-90f6-32f4328b68dd"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Fact Origin"; InternalName = "FactOrigin"; Id = [Guid]"f7a69053-5708-5a4a-b675-faf442a044d8"; Type = "Choice"; Choices = @("human_confirmed"); DefaultValue = "human_confirmed"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Defaulted Fields JSON"; InternalName = "DefaultedFieldsJson"; Id = [Guid]"be2f5a07-6976-5368-9dda-f74aee0e14f1"; Type = "Note"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Work Capture Revision"; InternalName = "WorkCaptureRevision"; Id = [Guid]"d0d74c4c-0f6a-5ceb-94a2-1d7fae8c76e4"; Type = "Number"; Choices = @(); DefaultValue = "1"; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Supersedes Work Capture ID"; InternalName = "SupersedesWorkCaptureID"; Id = [Guid]"3a4e09da-5d1d-58a0-b134-8c42304ac469"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Correction Reason"; InternalName = "CorrectionReason"; Id = [Guid]"625220c1-02a6-5f88-9aaa-b09918c24bfe"; Type = "Note"; Choices = @(); DefaultValue = $null; Indexed = $false; Unique = $false }
    [pscustomobject]@{ DisplayName = "Work Capture Payload Hash"; InternalName = "WorkCapturePayloadHash"; Id = [Guid]"5ff7b5b1-d0a6-5a17-8bab-246b61e5480c"; Type = "Text"; Choices = @(); DefaultValue = $null; Indexed = $true; Unique = $false }
)

$actualManifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualManifestHash -cne $requiredManifestHash) {
    Stop-Activation (
        "Manifest hash mismatch. Expected $requiredManifestHash; " +
        "found $actualManifestHash."
    )
}

Import-Module PnP.PowerShell -ErrorAction Stop
$connection = Connect-PnPOnline `
    -Url $siteUrl `
    -Interactive `
    -ClientId $clientId `
    -ReturnConnection

if (-not (Test-EquivalentSharePointSiteUrl `
    -ExpectedUrl $siteUrl `
    -ActualUrl $connection.Url
)) {
    Stop-Activation "Connected site '$($connection.Url)' is not '$siteUrl'."
}

$list = Get-PnPList -Identity $workLogId -Connection $connection
if ($list.Id -ne $workLogId -or $list.Title -cne "Work Log") {
    Stop-Activation (
        "Resolved list '$($list.Title)' ($($list.Id)); expected Work Log " +
        "($workLogId)."
    )
}

$fieldIncludes = @(
    "InternalName", "Title", "TypeAsString", "Required", "ReadOnlyField",
    "Hidden", "DefaultValue", "Indexed", "EnforceUniqueValues", "SchemaXml", "Id"
)
$initialFields = @(Get-PnPField -List $list -Includes $fieldIncludes -Connection $connection)
$fieldMap = @{}
foreach ($field in $initialFields) {
    if ($fieldMap.ContainsKey($field.InternalName)) {
        Stop-Activation "Duplicate internal field name '$($field.InternalName)'."
    }
    $fieldMap[$field.InternalName] = $field
}

Assert-ExistingField $fieldMap "ProjectLookup" "Lookup" $projectsId
Assert-ExistingField $fieldMap "ClientLookup" "Lookup" $clientsId
Assert-ExistingField $fieldMap "ActionLookup" "Lookup" $actionsId
Assert-ExistingField $fieldMap "WorkDate" "DateTime"
Assert-ExistingField $fieldMap "Hours" "Number"
Assert-ExistingField $fieldMap "WorkType" "Choice" -RequiredChoices @("Field Work")
Assert-ExistingField $fieldMap "TechnicalSummary" "Note"
Assert-ExistingField $fieldMap "Billable" "Boolean"
Assert-ExistingField $fieldMap "RateCode" "Choice" -RequiredChoices @(
    "APEX-95", "Scheduled Night-135"
)
Assert-ExistingField $fieldMap "TaskReference" "Text"
Assert-ExistingField $fieldMap "Project" "Text"
Assert-ExistingField $fieldMap "Client" "Text"

$plannedCreates = [Collections.Generic.List[object]]::new()
$compatibleExisting = [Collections.Generic.List[string]]::new()
foreach ($definition in $definitions) {
    $idCollisions = @(
        $initialFields | Where-Object {
            $_.Id -eq $definition.Id -and
            $_.InternalName -cne $definition.InternalName
        }
    )
    if ($idCollisions.Count -gt 0) {
        Stop-Activation (
            "Field ID '$($definition.Id)' already belongs to internal field " +
            "'$($idCollisions[0].InternalName)'."
        )
    }
    $displayNameCollisions = @(
        $initialFields | Where-Object {
            $_.Title -ceq $definition.DisplayName -and
            $_.InternalName -cne $definition.InternalName
        }
    )
    if ($displayNameCollisions.Count -gt 0) {
        Stop-Activation (
            "Display name '$($definition.DisplayName)' already belongs to " +
            "internal field '$($displayNameCollisions[0].InternalName)'."
        )
    }
    if ($fieldMap.ContainsKey($definition.InternalName)) {
        Assert-NewFieldCompatible $fieldMap[$definition.InternalName] $definition
        $compatibleExisting.Add($definition.InternalName)
    }
    else {
        $plannedCreates.Add($definition)
    }
}

$initialViews = @(Get-PnPView -List $list -Includes @(
    "Id", "Title", "DefaultView", "RowLimit", "Paged", "ViewQuery", "ViewFields"
) -Connection $connection)
$initialWebhooks = @(Get-PnPWebhookSubscription -List $list -Connection $connection)
$originalFieldIds = [Guid[]]@($initialFields | ForEach-Object { $_.Id })
$beforeSnapshot = Get-ExistingSchemaSnapshot `
    -Fields $initialFields `
    -OriginalFieldIds $originalFieldIds `
    -Views $initialViews `
    -Webhooks $initialWebhooks

Write-Host "Preflight PASS: exact manifest, site, list, canonical fields, views, and webhooks verified."
Write-Host "Plan: create $($plannedCreates.Count); reuse $($compatibleExisting.Count); change existing 0."

$created = [Collections.Generic.List[string]]::new()
foreach ($definition in $plannedCreates) {
    if ($PSCmdlet.ShouldProcess(
        "Work Log/$($definition.InternalName)",
        "Create optional $($definition.Type) field"
    )) {
        $fieldXml = New-UwcFieldXml $definition
        [void](Add-PnPFieldFromXml `
            -List $list `
            -FieldXml $fieldXml `
            -Connection $connection)
        $created.Add($definition.InternalName)
    }
}

if ($WhatIfPreference) {
    Write-Host "WhatIf PASS: preflight completed; no field was created."
    return
}

$finalFields = @(Get-PnPField -List $list -Includes $fieldIncludes -Connection $connection)
$finalFieldMap = @{}
foreach ($field in $finalFields) {
    $finalFieldMap[$field.InternalName] = $field
}
foreach ($definition in $definitions) {
    if (-not $finalFieldMap.ContainsKey($definition.InternalName)) {
        Stop-Activation "Post-verification field '$($definition.InternalName)' is missing."
    }
    Assert-NewFieldCompatible $finalFieldMap[$definition.InternalName] $definition
}

$finalViews = @(Get-PnPView -List $list -Includes @(
    "Id", "Title", "DefaultView", "RowLimit", "Paged", "ViewQuery", "ViewFields"
) -Connection $connection)
$finalWebhooks = @(Get-PnPWebhookSubscription -List $list -Connection $connection)
$afterSnapshot = Get-ExistingSchemaSnapshot `
    -Fields $finalFields `
    -OriginalFieldIds $originalFieldIds `
    -Views $finalViews `
    -Webhooks $finalWebhooks

if ($beforeSnapshot.Hash -cne $afterSnapshot.Hash) {
    Stop-Activation (
        "Existing field, view, or webhook schema changed unexpectedly. " +
        "Before=$($beforeSnapshot.Hash), after=$($afterSnapshot.Hash)."
    )
}

$reused = @($definitions.InternalName | Where-Object { $created -cnotcontains $_ })
Write-Host ""
Write-Host "Universal Work Capture V1 Work Log schema: PASS"
Write-Host "Site: $siteUrl"
Write-Host "List: Work Log ($workLogId)"
Write-Host "Manifest SHA-256: $actualManifestHash"
Write-Host "Created ($($created.Count)): $($created -join ', ')"
Write-Host "Reused compatible ($($reused.Count)): $($reused -join ', ')"
Write-Host "Approved V1 fields verified: $($definitions.Count)"
Write-Host "Original fields unchanged: $($afterSnapshot.FieldCount)"
Write-Host "Views unchanged: $($afterSnapshot.ViewCount)"
Write-Host "Webhook subscriptions unchanged: $($afterSnapshot.WebhookCount)"
Write-Host "Existing values read or changed: 0"
Write-Host "Rate, finance, permission, view, and webhook mutations: 0"
