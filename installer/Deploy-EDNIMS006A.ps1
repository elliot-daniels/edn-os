#Requires -Version 7.2
<#+
.SYNOPSIS
Plans or applies the approved additive optional-field increment IMS-006A.

.DESCRIPTION
The generic engine consumes a validated manifest. Plan performs schema reads
only. Apply permits only Add-PnPField for manifest fields and requires an
approval identifier plus the exact manifest SHA-256. Live use requires a
separate recorded GO decision.
#>
[CmdletBinding()]
param(
    [uri] $SiteUrl,
    [string] $ClientId,
    [string] $Tenant,
    [string] $ManifestPath,
    [ValidateSet('Plan', 'Apply')] [string] $Mode = 'Plan',
    [string] $ApprovalId,
    [string] $ApprovedManifestSha256,
    [string] $OutputDirectory,
    [switch] $AllowRepositoryOutput,
    [datetimeoffset] $GeneratedAt = [datetimeoffset]::UtcNow
)

$script:Edn006AScriptVersion = '1.0.0'
$script:Edn006ASchemaVersion = '1.0.0'
$script:Edn006AAllowedTypes = @('Text', 'Note', 'Choice', 'DateTime', 'URL', 'User')

function Protect-Edn006AMessage {
    param([AllowNull()] [string] $Message)
    if ([string]::IsNullOrWhiteSpace($Message)) { return 'No error message available.' }
    $safe = $Message -replace '(?i)Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]'
    $safe = $safe -replace '(?i)(client[_ -]?secret|password|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*\S+', '$1=[REDACTED]'
    if ($safe.Length -gt 500) { return $safe.Substring(0, 500) }
    return $safe
}

function Resolve-Edn006AOutputPath {
    param([string] $Path, [string] $RepositoryRoot, [switch] $AllowRepository)
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'OutputDirectory must be explicitly supplied.' }
    $full = [IO.Path]::GetFullPath($Path)
    $repo = [IO.Path]::GetFullPath($RepositoryRoot)
    $comparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    $prefix = $repo.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (($full.Equals($repo, $comparison) -or $full.StartsWith($prefix, $comparison)) -and -not $AllowRepository) {
        throw 'OutputDirectory must be outside the repository.'
    }
    return $full
}

function Read-Edn006AManifest {
    param([Parameter(Mandatory)] [string] $Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'ManifestPath does not exist.' }
    $manifest = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json -Depth 30
    if ($manifest.schema_version -ne $script:Edn006ASchemaVersion -or $manifest.increment -ne 'IMS-006A') {
        throw 'Manifest schema version or increment is unsupported.'
    }
    if ($manifest.mode -ne 'additive_optional_fields_only') { throw 'Manifest does not authorize additive optional fields only.' }
    if (@($manifest.fields).Count -eq 0) { throw 'Manifest contains no fields.' }
    $seen = @{}
    foreach ($field in @($manifest.fields)) {
        foreach ($requiredProperty in @('list', 'list_id', 'display_name', 'internal_name', 'type')) {
            if ([string]::IsNullOrWhiteSpace([string]$field.$requiredProperty)) { throw "Manifest field is missing $requiredProperty." }
        }
        $parsedGuid = [guid]::Empty
        if (-not [guid]::TryParse([string]$field.list_id, [ref]$parsedGuid)) { throw "Invalid list_id for $($field.internal_name)." }
        if ([string]$field.internal_name -notmatch '^IMS[A-Za-z0-9]+$') { throw "Unsafe internal name: $($field.internal_name)" }
        if ([string]$field.type -notin $script:Edn006AAllowedTypes) { throw "Unsupported field type: $($field.type)" }
        if ($field.PSObject.Properties.Name -contains 'required' -and [bool]$field.required) { throw 'IMS-006A refuses required fields.' }
        if ($field.PSObject.Properties.Name -contains 'lookup_target') { throw 'IMS-006A refuses lookup fields.' }
        $key = "$($field.list_id)|$($field.internal_name)".ToLowerInvariant()
        if ($seen.ContainsKey($key)) { throw "Duplicate manifest field: $key" }
        $seen[$key] = $true
        if ($field.type -eq 'Choice' -and @($field.choices).Count -lt 1) { throw "Choice field has no choices: $($field.internal_name)" }
    }
    return $manifest
}

function Get-Edn006AManifestHash {
    param([Parameter(Mandatory)] [string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-Edn006AFieldCompatibility {
    param([Parameter(Mandatory)] [object] $Desired, [AllowNull()] [object] $Existing)
    if ($null -eq $Existing) { return 'missing' }
    $existingType = [string]$Existing.TypeAsString
    $typeMap = @{ URL = 'URL'; Text = 'Text'; Note = 'Note'; Choice = 'Choice'; DateTime = 'DateTime'; User = 'User' }
    if ($existingType -ne $typeMap[[string]$Desired.type]) { return 'incompatible' }
    if ($Existing.Required -eq $true) { return 'incompatible' }
    if ($Desired.type -eq 'Choice') {
        $actual = @($Existing.Choices | ForEach-Object { [string]$_ } | Sort-Object)
        $wanted = @($Desired.choices | ForEach-Object { [string]$_ } | Sort-Object)
        if (($actual -join "`n") -ne ($wanted -join "`n")) { return 'incompatible' }
    }
    return 'compatible'
}

function New-Edn006AFieldParameters {
    param([Parameter(Mandatory)] [object] $Field)
    $parameters = @{
        List = [guid]$Field.list_id
        DisplayName = [string]$Field.display_name
        InternalName = [string]$Field.internal_name
        Type = [string]$Field.type
        Required = $false
    }
    if ($Field.type -eq 'Choice') { $parameters.Choices = @($Field.choices) }
    return $parameters
}

function Get-Edn006APlan {
    param([Parameter(Mandatory)] [object] $Manifest)
    $results = @()
    foreach ($group in @($Manifest.fields | Group-Object list_id | Sort-Object Name)) {
        $desiredListName = [string]$group.Group[0].list
        $list = Get-PnPList -Identity ([guid]$group.Name) -Includes Id,Title,RootFolder
        if ($null -eq $list -or ([guid]$list.Id).ToString('D') -ne ([guid]$group.Name).ToString('D')) {
            throw "Target list identity validation failed for $desiredListName."
        }
        if ([string]$list.Title -ne $desiredListName) { throw "Target list title mismatch for $desiredListName." }
        $existingFields = @(Get-PnPField -List ([guid]$group.Name))
        foreach ($field in @($group.Group | Sort-Object internal_name)) {
            $existing = @($existingFields | Where-Object { $_.InternalName -ieq [string]$field.internal_name })
            if ($existing.Count -gt 1) { throw "Duplicate existing internal field name: $($field.internal_name)" }
            $state = Test-Edn006AFieldCompatibility -Desired $field -Existing ($existing | Select-Object -First 1)
            $action = if ($state -eq 'missing') { if ($Mode -eq 'Apply') { 'create' } else { 'would_create' } } elseif ($state -eq 'compatible') { 'already_compliant' } else { 'incompatible' }
            $results += [pscustomobject][ordered]@{ list = $desiredListName; list_id = ([guid]$group.Name).ToString('D').ToLowerInvariant(); internal_name = [string]$field.internal_name; type = [string]$field.type; state = $state; action = $action }
        }
    }
    return @($results)
}

function Invoke-Edn006AApply {
    param([Parameter(Mandatory)] [object] $Manifest, [Parameter(Mandatory)] [object[]] $Plan)
    if (@($Plan | Where-Object state -eq 'incompatible').Count -gt 0) { throw 'Apply refused because incompatible fields exist.' }
    $results = @()
    foreach ($entry in @($Plan)) {
        if ($entry.state -eq 'compatible') { $results += $entry; continue }
        $field = $Manifest.fields | Where-Object { $_.list_id -eq $entry.list_id -and $_.internal_name -eq $entry.internal_name } | Select-Object -First 1
        try {
            $fieldParameters = New-Edn006AFieldParameters -Field $field
            Add-PnPField @fieldParameters | Out-Null
            $entry.action = 'created'
            $results += $entry
        } catch {
            $entry.action = 'failed'
            $entry | Add-Member -NotePropertyName error -NotePropertyValue (Protect-Edn006AMessage $_.Exception.Message)
            $results += $entry
            throw "Field creation failed for $($entry.internal_name): $(Protect-Edn006AMessage $_.Exception.Message)"
        }
    }
    return @($results)
}

function Write-Edn006AReport {
    param([string] $Path, [object] $Value)
    if (Test-Path -LiteralPath $Path) { throw "Output already exists: $Path" }
    $json = $Value | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($Path, $json + "`n", [Text.UTF8Encoding]::new($false))
}

function Invoke-Edn006ADeployment {
    $repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    foreach ($value in @($SiteUrl, $ClientId, $Tenant, $ManifestPath, $OutputDirectory)) {
        if ([string]::IsNullOrWhiteSpace([string]$value)) { throw 'SiteUrl, ClientId, Tenant, ManifestPath and OutputDirectory are required.' }
    }
    $manifest = Read-Edn006AManifest -Path $ManifestPath
    $manifestHash = Get-Edn006AManifestHash -Path $ManifestPath
    if ($Mode -eq 'Apply') {
        if ([string]::IsNullOrWhiteSpace($ApprovalId)) { throw 'Apply requires an explicit ApprovalId.' }
        if ($ApprovedManifestSha256.ToLowerInvariant() -ne $manifestHash) { throw 'Approved manifest hash does not match.' }
    }
    $output = Resolve-Edn006AOutputPath -Path $OutputDirectory -RepositoryRoot $repoRoot -AllowRepository:$AllowRepositoryOutput
    if (-not (Test-Path -LiteralPath $output -PathType Container)) { throw 'OutputDirectory must already exist.' }
    $reportPath = Join-Path $output "ims-006a-$($Mode.ToLowerInvariant())-report.json"
    if (Test-Path -LiteralPath $reportPath) { throw "Output already exists: $reportPath" }
    Import-Module PnP.PowerShell -ErrorAction Stop
    Connect-PnPOnline -Url $SiteUrl.AbsoluteUri -ClientId $ClientId -Tenant $Tenant -Interactive -ErrorAction Stop
    try {
        $plan = Get-Edn006APlan -Manifest $manifest
        $results = if ($Mode -eq 'Apply') { Invoke-Edn006AApply -Manifest $manifest -Plan $plan } else { $plan }
        $report = [pscustomobject][ordered]@{ schema_version = $script:Edn006ASchemaVersion; script_version = $script:Edn006AScriptVersion; increment = 'IMS-006A'; mode = $Mode.ToLowerInvariant(); generated_at_utc = $GeneratedAt.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'); manifest_sha256 = $manifestHash; approval_id = if ($Mode -eq 'Apply') { $ApprovalId } else { $null }; counts = [ordered]@{ total = @($results).Count; would_create = @($results | Where-Object action -eq 'would_create').Count; created = @($results | Where-Object action -eq 'created').Count; already_compliant = @($results | Where-Object action -eq 'already_compliant').Count; incompatible = @($results | Where-Object action -eq 'incompatible').Count; failed = @($results | Where-Object action -eq 'failed').Count }; results = @($results | Sort-Object list,internal_name) }
        Write-Edn006AReport -Path $reportPath -Value $report
        return $report
    } finally {
        Disconnect-PnPOnline -ErrorAction SilentlyContinue
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-Edn006ADeployment }
