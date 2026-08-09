#Requires -Version 7.2
<#
.SYNOPSIS
Compares an EDN SharePoint inventory with the approved IMS architecture offline.

.DESCRIPTION
Reads IMS-001 JSON files without changing them and writes deterministic gap
assessment JSON and Markdown to an explicit external directory. This script has
no SharePoint, authentication, network, Git, or operational-system commands.
#>
[CmdletBinding()]
param(
    [string] $InventoryDirectory,
    [string] $OutputDirectory,
    [switch] $AllowIncompleteInventory,
    [switch] $AllowRepositoryOutput,
    [datetimeoffset] $GeneratedAt = [datetimeoffset]::UtcNow
)

$script:GapSchemaVersion = '1.0.0'
$script:GapScriptVersion = '1.0.0'
$script:SupportedInventorySchema = '1.0.0'
$script:InventoryFiles = @(
    'inventory-summary.json',
    'sites.json',
    'lists-and-libraries.json',
    'fields.json',
    'content-types.json',
    'views.json',
    'permissions.json',
    'automation-references.json',
    'retention-metadata.json',
    'discovery-errors.json'
)
$script:GapOutputFiles = @(
    'gap-summary.json',
    'object-recommendations.json',
    'duplicate-candidates.json',
    'unresolved-decisions.json',
    'inventory-quality.json',
    'EDN-SharePoint-Gap-Assessment-Generated.md'
)
$script:AuthoritativeNames = @(
    'Projects', 'Clients', 'Actions', 'Assets', 'Approvals',
    'Executive Metrics', 'System Status', 'Work Log', 'Quotes',
    'Engineering Knowledge'
)
$script:ProposedNames = @(
    'Obligations and Requirements', 'Processes and Controls',
    'Risks and Opportunities', 'Assurance, Events and Findings',
    'Controlled Documents'
)
$script:GenericFields = @(
    'id', 'title', 'created', 'modified', 'author', 'editor',
    'contenttype', 'contenttypeid', 'attachments', 'version'
)

function Read-GapProperty {
    param(
        [AllowNull()] [object] $InputObject,
        [Parameter(Mandatory)] [string] $Name
    )

    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [System.Collections.IDictionary]) {
        if ($InputObject.Contains($Name)) { return $InputObject[$Name] }
        return $null
    }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function Test-GapSecretName {
    param([Parameter(Mandatory)] [string] $Name)

    return $Name -match '(?i)^(authorization|cookie|credential|password|clientsecret|client_secret|access.?token|refresh.?token|id.?token|private.?key|certificate.?password)$'
}

function ConvertTo-GapSafeValue {
    param([AllowNull()] [object] $InputObject)

    if ($null -eq $InputObject) { return $null }
    if ($InputObject -is [string]) {
        if ($InputObject -match '(?i)^\s*Bearer\s+[A-Za-z0-9._~+/=-]+\s*$') {
            return '[REDACTED]'
        }
        return $InputObject
    }
    if ($InputObject -is [guid]) { return $InputObject.ToString('D').ToLowerInvariant() }
    if ($InputObject -is [datetimeoffset]) {
        return $InputObject.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    }
    if ($InputObject -is [datetime]) {
        return ([datetimeoffset]$InputObject).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    }
    if ($InputObject -is [bool] -or $InputObject -is [ValueType]) { return $InputObject }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $safe = [ordered]@{}
        foreach ($key in @($InputObject.Keys | ForEach-Object { [string]$_ } | Sort-Object)) {
            if (-not (Test-GapSecretName $key)) {
                $safe[$key] = ConvertTo-GapSafeValue $InputObject[$key]
            }
        }
        return [pscustomobject]$safe
    }
    if ($InputObject -is [System.Collections.IEnumerable]) {
        return @($InputObject | ForEach-Object { ConvertTo-GapSafeValue $_ })
    }
    $safe = [ordered]@{}
    foreach ($property in @($InputObject.PSObject.Properties | Sort-Object Name)) {
        if (-not (Test-GapSecretName $property.Name)) {
            $safe[$property.Name] = ConvertTo-GapSafeValue $property.Value
        }
    }
    return [pscustomobject]$safe
}

function Normalize-GapName {
    param([AllowNull()] [string] $Name)

    if ([string]::IsNullOrWhiteSpace($Name)) { return '' }
    $normalized = $Name.ToLowerInvariant() -replace '&', ' and '
    $tokens = @($normalized -split '[^a-z0-9]+' | Where-Object { $_ })
    $tokens = @($tokens | ForEach-Object {
        if ($_.Length -gt 4 -and $_.EndsWith('s') -and -not $_.EndsWith('ss')) {
            $_.Substring(0, $_.Length - 1)
        } else { $_ }
    })
    return ($tokens -join ' ')
}

function Get-GapTokens {
    param([AllowNull()] [string] $Name)
    return @((Normalize-GapName $Name) -split ' ' | Where-Object { $_ })
}

function Measure-GapOverlap {
    param([string[]] $Left, [string[]] $Right)

    $leftSet = @($Left | Sort-Object -Unique)
    $rightSet = @($Right | Sort-Object -Unique)
    if ($leftSet.Count -eq 0 -or $rightSet.Count -eq 0) { return 0.0 }
    $intersection = @($leftSet | Where-Object { $_ -in $rightSet }).Count
    $union = @($leftSet + $rightSet | Sort-Object -Unique).Count
    if ($union -eq 0) { return 0.0 }
    return [math]::Round($intersection / $union, 4)
}

function Resolve-GapOutputPath {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [string] $RepositoryRoot,
        [switch] $AllowRepository
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'OutputDirectory must be explicitly supplied.'
    }
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $repoPath = [System.IO.Path]::GetFullPath($RepositoryRoot)
    $comparison = if ($IsWindows) {
        [System.StringComparison]::OrdinalIgnoreCase
    } else { [System.StringComparison]::Ordinal }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $inside = $fullPath.Equals($repoPath, $comparison) -or
        $fullPath.StartsWith($repoPath.TrimEnd($separator) + $separator, $comparison)
    if ($inside -and -not $AllowRepository) {
        throw 'OutputDirectory must be outside the repository.'
    }
    return $fullPath
}

function Get-GapDirectoryFingerprint {
    param([Parameter(Mandatory)] [string] $Path, [string[]] $FileNames)

    $builder = [System.Text.StringBuilder]::new()
    foreach ($name in @($FileNames | Sort-Object)) {
        $filePath = [System.IO.Path]::Combine($Path, $name)
        if ([System.IO.File]::Exists($filePath)) {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $hash = [System.Security.Cryptography.SHA256]::HashData($bytes)
            [void]$builder.Append($name).Append(':').Append(
                [Convert]::ToHexString($hash).ToLowerInvariant()
            ).Append("`n")
        } else {
            [void]$builder.Append($name).Append(':missing').Append("`n")
        }
    }
    $manifestBytes = [System.Text.Encoding]::UTF8.GetBytes($builder.ToString())
    return [Convert]::ToHexString(
        [System.Security.Cryptography.SHA256]::HashData($manifestBytes)
    ).ToLowerInvariant()
}

function Read-GapInventory {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [switch] $AllowIncomplete
    )

    if (-not [System.IO.Directory]::Exists($Path)) {
        throw 'InventoryDirectory does not exist.'
    }
    $documents = [ordered]@{}
    $quality = [System.Collections.Generic.List[object]]::new()
    foreach ($name in $script:InventoryFiles) {
        $filePath = [System.IO.Path]::Combine($Path, $name)
        if (-not [System.IO.File]::Exists($filePath)) {
            $quality.Add([ordered]@{
                severity = 'error'; code = 'missing_file'; source_file = $name
                message = 'Expected inventory file is missing.'
            })
            if (-not $AllowIncomplete) { throw "Incomplete inventory: missing $name" }
            continue
        }
        try {
            $document = [System.IO.File]::ReadAllText($filePath) | ConvertFrom-Json
        } catch {
            throw "Malformed inventory JSON: $name"
        }
        if ($null -eq $document -or $document -is [string]) {
            throw "Malformed inventory envelope: $name"
        }
        if ((Read-GapProperty $document 'schema_version') -ne $script:SupportedInventorySchema) {
            throw "Unsupported inventory schema in ${name}: $($document.schema_version)"
        }
        $recordsProperty = $document.PSObject.Properties['records']
        if ($null -eq $recordsProperty -or $recordsProperty.Value -is [string]) {
            throw "Malformed records collection: $name"
        }
        $documents[$name] = $document
    }

    $siteUrls = @($documents.Values | ForEach-Object { $_.site_url } |
        Where-Object { $_ } | Sort-Object -Unique)
    if ($siteUrls.Count -gt 1) { throw 'Inventory files contain inconsistent site URLs.' }
    $timestamps = @($documents.Values | ForEach-Object { $_.generated_at_utc } |
        Where-Object { $_ } | Sort-Object -Unique)
    if ($timestamps.Count -gt 1) {
        $quality.Add([ordered]@{
            severity = 'warning'; code = 'mixed_timestamps'; source_file = '*'
            message = 'Inventory envelopes have different generation timestamps.'
        })
    }
    $unavailable = @($documents.Values | ForEach-Object { $_.unavailable_sections } |
        Where-Object { $_ } | Sort-Object -Unique)
    foreach ($section in $unavailable) {
        $quality.Add([ordered]@{
            severity = 'warning'; code = 'unavailable_section'; source_file = '*'
            message = "Discovery section unavailable: $section"
        })
    }
    return [pscustomobject]@{
        Documents = $documents
        Quality = $quality
        SiteUrl = if ($siteUrls.Count -eq 1) { $siteUrls[0] } else { $null }
        InventoryTimestamp = if ($timestamps.Count -ge 1) { $timestamps[0] } else { $null }
        Unavailable = $unavailable
    }
}

function Get-GapRecords {
    param([object] $Inventory, [string] $FileName)
    if (-not $Inventory.Documents.Contains($FileName)) { return @() }
    return @($Inventory.Documents[$FileName].records)
}

function Build-GapDuplicates {
    param([object[]] $Lists, [object[]] $Fields)

    $result = [System.Collections.Generic.List[object]]::new()
    $fieldPresence = @{}
    foreach ($field in $Fields) {
        $internalName = [string]$field.internal_name
        $normalizedField = Normalize-GapName $internalName
        if ($field.hidden -eq $true -or $field.field_type -eq 'Computed' -or
            $internalName.StartsWith('_') -or [string]::IsNullOrWhiteSpace($normalizedField) -or
            $normalizedField -in $script:GenericFields) {
            continue
        }
        if (-not $fieldPresence.ContainsKey($normalizedField)) {
            $fieldPresence[$normalizedField] = [System.Collections.Generic.HashSet[string]]::new()
        }
        [void]$fieldPresence[$normalizedField].Add([string]$field.list_id)
    }
    $maximumCommonLists = [math]::Max(2, [math]::Floor($Lists.Count * 0.1))
    for ($leftIndex = 0; $leftIndex -lt $Lists.Count; $leftIndex++) {
        for ($rightIndex = $leftIndex + 1; $rightIndex -lt $Lists.Count; $rightIndex++) {
            $left = $Lists[$leftIndex]
            $right = $Lists[$rightIndex]
            $leftName = Normalize-GapName ([string]$left.name)
            $rightName = Normalize-GapName ([string]$right.name)
            $nameScore = Measure-GapOverlap (Get-GapTokens $left.name) (Get-GapTokens $right.name)
            $leftFields = @($Fields | Where-Object {
                $_.list_id -eq $left.list_id -and $_.hidden -ne $true -and
                $_.field_type -ne 'Computed' -and
                -not ([string]$_.internal_name).StartsWith('_')
            } |
                ForEach-Object { Normalize-GapName $_.internal_name } |
                Where-Object {
                    $_ -and $_ -notin $script:GenericFields -and
                    $fieldPresence.ContainsKey($_) -and
                    $fieldPresence[$_].Count -le $maximumCommonLists
                } | Sort-Object -Unique)
            $rightFields = @($Fields | Where-Object {
                $_.list_id -eq $right.list_id -and $_.hidden -ne $true -and
                $_.field_type -ne 'Computed' -and
                -not ([string]$_.internal_name).StartsWith('_')
            } |
                ForEach-Object { Normalize-GapName $_.internal_name } |
                Where-Object {
                    $_ -and $_ -notin $script:GenericFields -and
                    $fieldPresence.ContainsKey($_) -and
                    $fieldPresence[$_].Count -le $maximumCommonLists
                } | Sort-Object -Unique)
            $fieldScore = Measure-GapOverlap $leftFields $rightFields
            $exact = $leftName -and $leftName -eq $rightName
            if ($exact -or $nameScore -ge 0.6 -or
                ($leftFields.Count -ge 2 -and $rightFields.Count -ge 2 -and $fieldScore -ge 0.6)) {
                $result.Add([ordered]@{
                    candidate_id = "$($left.list_id)|$($right.list_id)"
                    left_list_id = $left.list_id
                    left_name = $left.name
                    right_list_id = $right.list_id
                    right_name = $right.name
                    exact_normalized_name = [bool]$exact
                    name_overlap = $nameScore
                    field_overlap = $fieldScore
                    shared_fields = @($leftFields | Where-Object { $_ -in $rightFields })
                    evidence_paths = @(
                        "lists-and-libraries.json#/records/$leftIndex",
                        "lists-and-libraries.json#/records/$rightIndex"
                    )
                    decision = 'Needs owner decision'
                    risk = 'Possible duplicate source of truth; automation, permissions, retention, and data ownership require review.'
                })
            }
        }
    }
    return @($result | Sort-Object candidate_id)
}

function Find-GapTarget {
    param([object] $List)

    $name = Normalize-GapName ([string]$List.name)
    foreach ($target in $script:AuthoritativeNames) {
        if ($name -eq (Normalize-GapName $target)) {
            return [pscustomobject]@{ Name = $target; Kind = 'authoritative'; Score = 1.0 }
        }
    }
    foreach ($target in $script:ProposedNames) {
        if ($name -eq (Normalize-GapName $target)) {
            return [pscustomobject]@{ Name = $target; Kind = 'proposed'; Score = 1.0 }
        }
    }
    $best = $null
    foreach ($target in @($script:AuthoritativeNames + $script:ProposedNames)) {
        $score = Measure-GapOverlap (Get-GapTokens $List.name) (Get-GapTokens $target)
        if ($score -ge 0.5 -and ($null -eq $best -or $score -gt $best.Score)) {
            $kind = if ($target -in $script:AuthoritativeNames) { 'authoritative' } else { 'proposed' }
            $best = [pscustomobject]@{ Name = $target; Kind = $kind; Score = $score }
        }
    }
    return $best
}

function Build-GapRecommendation {
    param(
        [object] $List,
        [int] $Index,
        [object] $Target,
        [object[]] $Fields,
        [object[]] $ContentTypes,
        [object[]] $Permissions,
        [object[]] $Views,
        [object[]] $Automation,
        [object[]] $Retention,
        [object[]] $Duplicates,
        [string[]] $Unavailable
    )

    $listFields = @($Fields | Where-Object { $_.list_id -eq $List.list_id } |
        Sort-Object internal_name | ForEach-Object {
            [ordered]@{ field_id = $_.field_id; internal_name = $_.internal_name; field_type = $_.field_type }
        })
    $listTypes = @($ContentTypes | Where-Object { $_.list_id -eq $List.list_id } |
        Sort-Object content_type_id | ForEach-Object {
            [ordered]@{ content_type_id = $_.content_type_id; name = $_.name }
        })
    $listPermissions = @($Permissions | Where-Object { $_.scope_type -eq 'list' -and $_.scope_id -eq $List.list_id })
    $listViews = @($Views | Where-Object { $_.list_id -eq $List.list_id } | Sort-Object view_id)
    $listAutomation = @($Automation | Where-Object { $_.list_id -eq $List.list_id } | Sort-Object reference_type, reference_id)
    $listRetention = @($Retention | Where-Object { $_.scope_id -eq $List.list_id })
    $listDuplicates = @($Duplicates | Where-Object {
        $_.left_list_id -eq $List.list_id -or $_.right_list_id -eq $List.list_id
    })
    $risks = [System.Collections.Generic.List[string]]::new()
    $questions = [System.Collections.Generic.List[string]]::new()
    if ($List.has_unique_permissions -eq $true -or $listPermissions.Count -gt 0) {
        $risks.Add('Permissions require owner and least-privilege review.')
    }
    if ($List.versioning_enabled -eq $false) {
        $risks.Add('Versioning is observed disabled.')
    }
    if ($listAutomation.Count -gt 0) {
        $risks.Add('Automation dependencies require impact analysis before change or consolidation.')
    }
    if ($listRetention.Count -eq 0) {
        if ('retention_metadata' -in $Unavailable -or 'purview_policy_bodies' -in $Unavailable) {
            $questions.Add('Retention configuration is unknown because discovery was unavailable.')
        } else { $risks.Add('No list retention metadata record was observed.') }
    }
    if ($listDuplicates.Count -gt 0) {
        $risks.Add('One or more duplicate or overlap candidates require owner review.')
    }

    $classification = 'Out of IMS scope'
    $reason = 'No material match to the approved authoritative or proposed IMS names was found.'
    $confidence = 'medium'
    $owner = 'Business owner (unassigned)'
    if ($null -ne $Target) {
        $owner = if ($Target.Kind -eq 'authoritative') {
            "$($Target.Name) owner (unassigned)"
        } else { 'IMS owner (unassigned)' }
        if ($Target.Score -lt 1.0 -or $listDuplicates.Count -gt 0) {
            $classification = 'Needs owner decision'
            $reason = "Possible match to $($Target.Name), but identity or overlap is not conclusive."
            $confidence = 'low'
            $questions.Add("Is this object the authoritative implementation of $($Target.Name)?")
        } elseif ($Target.Kind -eq 'proposed') {
            $classification = 'Extend existing'
            $reason = "Existing object matches proposed shared structure $($Target.Name); field-level adequacy still requires review."
            $confidence = 'medium'
        } elseif ($risks.Count -gt 0 -or $questions.Count -gt 0) {
            $classification = 'Extend existing'
            $reason = "Existing authoritative structure $($Target.Name) should be preserved, with identified control gaps reviewed."
            $confidence = 'high'
        } else {
            $classification = 'Reuse unchanged'
            $reason = "Exact match to existing authoritative structure $($Target.Name); no material gap was observed in available metadata."
            $confidence = 'high'
        }
    }

    return [ordered]@{
        recommendation_id = "list:$($List.list_id)"
        source_inventory_object = "lists-and-libraries.json#/records/$Index"
        list_id = $List.list_id
        name = $List.name
        internal_name = $List.internal_name
        object_type = $List.base_type
        url = $List.url
        architecture_target = if ($null -ne $Target) { $Target.Name } else { $null }
        target_kind = if ($null -ne $Target) { $Target.Kind } else { $null }
        classification = $classification
        confidence = $confidence
        reason = $reason
        relevant_fields = $listFields
        content_types = $listTypes
        permissions = [ordered]@{
            has_unique_permissions = $List.has_unique_permissions
            assignments_observed = $listPermissions.Count
        }
        views = @($listViews | ForEach-Object { [ordered]@{ view_id = $_.view_id; name = $_.name } })
        versioning = [ordered]@{ enabled = $List.versioning_enabled; minor_enabled = $List.minor_versions_enabled }
        retention_indicators = $listRetention
        automation_dependencies = @($listAutomation | ForEach-Object {
            [ordered]@{ type = $_.reference_type; reference_id = $_.reference_id }
        })
        risks = @($risks | Sort-Object -Unique)
        proposed_owner = $owner
        unresolved_questions = @($questions | Sort-Object -Unique)
        unavailable_sections = @($Unavailable | Sort-Object -Unique)
        evidence_paths = @(
            "lists-and-libraries.json#/records/$Index",
            'fields.json#/records', 'content-types.json#/records',
            'permissions.json#/records', 'views.json#/records',
            'automation-references.json#/records', 'retention-metadata.json#/records'
        )
    }
}

function Build-GapEnvelope {
    param(
        [object] $Context,
        [object[]] $Records,
        [string[]] $Warnings = @()
    )
    return [ordered]@{
        schema_version = $script:GapSchemaVersion
        script_version = $script:GapScriptVersion
        inventory_schema_version = $script:SupportedInventorySchema
        inventory_generated_at_utc = $Context.InventoryTimestamp
        generated_at_utc = $Context.GeneratedAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
        inventory_fingerprint_sha256 = $Context.Fingerprint
        warnings = @($Warnings | Sort-Object -Unique)
        records = @($Records)
    }
}

function Write-GapJson {
    param([string] $Path, [object] $Value)
    $safe = ConvertTo-GapSafeValue $Value
    $json = $safe | ConvertTo-Json -Depth 50
    [System.IO.File]::WriteAllText(
        $Path, $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Build-GapMarkdown {
    param([object] $Context, [object[]] $Recommendations, [object[]] $Duplicates, [object[]] $Quality)

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine('# EDN SharePoint Gap Assessment — Generated')
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('This deterministic offline report is a decision aid, not approval to change SharePoint.')
    [void]$builder.AppendLine()
    [void]$builder.AppendLine("- Inventory schema: $($script:SupportedInventorySchema)")
    [void]$builder.AppendLine("- Inventory fingerprint: ``$($Context.Fingerprint)``")
    [void]$builder.AppendLine("- Analysis timestamp (UTC): $($Context.GeneratedAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'))")
    [void]$builder.AppendLine("- Recommendations: $($Recommendations.Count)")
    [void]$builder.AppendLine("- Duplicate candidates: $($Duplicates.Count)")
    [void]$builder.AppendLine("- Quality findings: $($Quality.Count)")
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('## Object recommendations')
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('| Object | Architecture target | Classification | Confidence | Evidence |')
    [void]$builder.AppendLine('|---|---|---|---|---|')
    foreach ($item in @($Recommendations | Sort-Object recommendation_id)) {
        $name = ([string]$item.name) -replace '\|', '\|'
        $target = ([string]$item.architecture_target) -replace '\|', '\|'
        [void]$builder.AppendLine("| $name | $target | $($item.classification) | $($item.confidence) | ``$($item.source_inventory_object)`` |")
    }
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('## Required human review')
    [void]$builder.AppendLine()
    foreach ($item in @($Recommendations | Where-Object {
        $_.classification -in @('Create new', 'Retire or consolidate', 'Needs owner decision') -or
        $_.risks.Count -gt 0 -or $_.unresolved_questions.Count -gt 0
    } | Sort-Object recommendation_id)) {
        [void]$builder.AppendLine("- **$($item.name)** — $($item.classification): $($item.reason)")
    }
    if ($Duplicates.Count -eq 0) { [void]$builder.AppendLine('- No duplicate candidate met the deterministic thresholds.') }
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('## Inventory quality')
    [void]$builder.AppendLine()
    if ($Quality.Count -eq 0) { [void]$builder.AppendLine('- No structural quality finding was recorded.') }
    foreach ($finding in @($Quality | Sort-Object code, source_file)) {
        [void]$builder.AppendLine("- **$($finding.severity)** ``$($finding.code)`` — $($finding.message)")
    }
    [void]$builder.AppendLine()
    [void]$builder.AppendLine('No recommendation authorizes provisioning, migration, consolidation, retirement, or deletion.')
    return $builder.ToString()
}

function Compare-EdnSharePointInventory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $SourceDirectory,
        [Parameter(Mandatory)] [string] $ReportDirectory,
        [switch] $PermitIncompleteInventory,
        [switch] $RepositoryOutputApproved,
        [datetimeoffset] $Timestamp = [datetimeoffset]::UtcNow
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $inventoryPath = [System.IO.Path]::GetFullPath($SourceDirectory)
    $reportPath = Resolve-GapOutputPath $ReportDirectory $repositoryRoot `
        -AllowRepository:$RepositoryOutputApproved
    if ($inventoryPath -eq $reportPath) {
        throw 'OutputDirectory must not be the inventory directory.'
    }
    foreach ($name in $script:GapOutputFiles) {
        if ([System.IO.File]::Exists([System.IO.Path]::Combine($reportPath, $name))) {
            throw "Refusing to overwrite existing report file: $name"
        }
    }

    $inventory = Read-GapInventory $inventoryPath -AllowIncomplete:$PermitIncompleteInventory
    $context = [pscustomobject]@{
        GeneratedAt = $Timestamp
        InventoryTimestamp = $inventory.InventoryTimestamp
        Fingerprint = Get-GapDirectoryFingerprint $inventoryPath $script:InventoryFiles
    }
    $lists = @(Get-GapRecords $inventory 'lists-and-libraries.json' | Sort-Object list_id)
    $fields = @(Get-GapRecords $inventory 'fields.json')
    $contentTypes = @(Get-GapRecords $inventory 'content-types.json')
    $views = @(Get-GapRecords $inventory 'views.json')
    $permissions = @(Get-GapRecords $inventory 'permissions.json')
    $automation = @(Get-GapRecords $inventory 'automation-references.json')
    $retention = @(Get-GapRecords $inventory 'retention-metadata.json')
    $duplicates = @(Build-GapDuplicates $lists $fields)

    $recommendations = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $lists.Count; $index++) {
        $target = Find-GapTarget $lists[$index]
        $recommendations.Add((Build-GapRecommendation -List $lists[$index] `
            -Index $index -Target $target -Fields $fields -ContentTypes $contentTypes `
            -Permissions $permissions -Views $views -Automation $automation `
            -Retention $retention -Duplicates $duplicates -Unavailable $inventory.Unavailable))
    }

    foreach ($target in $script:ProposedNames) {
        $matches = @($recommendations | Where-Object { $_.architecture_target -eq $target })
        if ($matches.Count -eq 0) {
            $relevantUnavailable = @($inventory.Unavailable | Where-Object {
                $_ -in @('lists', 'lists_and_libraries', 'fields', 'content_types')
            })
            $classification = if ($relevantUnavailable.Count -gt 0 -or $PermitIncompleteInventory) {
                'Needs owner decision'
            } else { 'Create new' }
            $reason = if ($classification -eq 'Create new') {
                'No exact, name-overlap, or field-overlap candidate was found in complete relevant discovery; creation remains subject to owner approval.'
            } else {
                'Relevant discovery is incomplete or unavailable, so absence cannot be established.'
            }
            $recommendations.Add([ordered]@{
                recommendation_id = "architecture:$((Normalize-GapName $target) -replace ' ', '-')"
                source_inventory_object = 'docs/ims/EDN-IMS-Architecture.md#new-shared-structures'
                list_id = $null; name = $target; internal_name = $null
                object_type = 'proposed_shared_structure'; url = $null
                architecture_target = $target; target_kind = 'proposed'
                classification = $classification; confidence = 'low'; reason = $reason
                relevant_fields = @(); content_types = @()
                permissions = [ordered]@{ has_unique_permissions = $null; assignments_observed = 0 }
                views = @(); versioning = [ordered]@{ enabled = $null; minor_enabled = $null }
                retention_indicators = @(); automation_dependencies = @()
                risks = @('Creating a duplicate structure would fragment the source of truth.')
                proposed_owner = 'IMS owner (unassigned)'
                unresolved_questions = @('Does a differently named live object already implement this capability?', 'Does the owner approve a new authoritative structure?')
                unavailable_sections = @($inventory.Unavailable | Sort-Object -Unique)
                evidence_paths = @('docs/ims/EDN-IMS-Architecture.md#new-shared-structures', 'lists-and-libraries.json#/records', 'fields.json#/records')
            })
        }
    }

    $sortedRecommendations = @($recommendations | Sort-Object recommendation_id)
    $unresolved = @($sortedRecommendations | Where-Object {
        $_.classification -in @('Create new', 'Retire or consolidate', 'Needs owner decision') -or
        $_.risks.Count -gt 0 -or $_.unresolved_questions.Count -gt 0
    } | ForEach-Object {
        [ordered]@{
            recommendation_id = $_.recommendation_id
            name = $_.name
            classification = $_.classification
            risks = $_.risks
            proposed_owner = $_.proposed_owner
            unresolved_questions = $_.unresolved_questions
            evidence_paths = $_.evidence_paths
        }
    })
    $quality = @($inventory.Quality | Sort-Object code, source_file)
    $warnings = @(
        'Recommendations are offline decision aids and do not authorize SharePoint changes.'
        if ($inventory.Unavailable.Count -gt 0) {
            'Unavailable discovery sections are treated as unknown, not absent.'
        }
    )
    $summaryRecord = [ordered]@{
        recommendation_count = $sortedRecommendations.Count
        duplicate_candidate_count = $duplicates.Count
        unresolved_count = $unresolved.Count
        quality_finding_count = $quality.Count
        classifications = [ordered]@{}
    }
    foreach ($classification in @('Reuse unchanged', 'Extend existing', 'Create new', 'Retire or consolidate', 'Needs owner decision', 'Out of IMS scope')) {
        $summaryRecord.classifications[$classification] = @($sortedRecommendations |
            Where-Object { $_.classification -eq $classification }).Count
    }

    [System.IO.Directory]::CreateDirectory($reportPath) | Out-Null
    Write-GapJson ([System.IO.Path]::Combine($reportPath, 'gap-summary.json')) `
        (Build-GapEnvelope $context @($summaryRecord) $warnings)
    Write-GapJson ([System.IO.Path]::Combine($reportPath, 'object-recommendations.json')) `
        (Build-GapEnvelope $context $sortedRecommendations $warnings)
    Write-GapJson ([System.IO.Path]::Combine($reportPath, 'duplicate-candidates.json')) `
        (Build-GapEnvelope $context $duplicates $warnings)
    Write-GapJson ([System.IO.Path]::Combine($reportPath, 'unresolved-decisions.json')) `
        (Build-GapEnvelope $context $unresolved $warnings)
    Write-GapJson ([System.IO.Path]::Combine($reportPath, 'inventory-quality.json')) `
        (Build-GapEnvelope $context $quality $warnings)
    $markdown = Build-GapMarkdown $context $sortedRecommendations $duplicates $quality
    [System.IO.File]::WriteAllText(
        [System.IO.Path]::Combine($reportPath, 'EDN-SharePoint-Gap-Assessment-Generated.md'),
        $markdown, [System.Text.UTF8Encoding]::new($false)
    )
    return [pscustomobject]@{
        OutputDirectory = $reportPath
        RecommendationCount = $sortedRecommendations.Count
        DuplicateCandidateCount = $duplicates.Count
        QualityFindingCount = $quality.Count
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    if ([string]::IsNullOrWhiteSpace($InventoryDirectory) -or
        [string]::IsNullOrWhiteSpace($OutputDirectory)) {
        throw 'InventoryDirectory and OutputDirectory are required.'
    }
    Compare-EdnSharePointInventory -SourceDirectory $InventoryDirectory `
        -ReportDirectory $OutputDirectory `
        -PermitIncompleteInventory:$AllowIncompleteInventory `
        -RepositoryOutputApproved:$AllowRepositoryOutput -Timestamp $GeneratedAt
}
