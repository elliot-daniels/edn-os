#Requires -Version 7.2
<#+
.SYNOPSIS
Exports a read-only, metadata-only SharePoint site inventory.

.DESCRIPTION
IMS-001 discovery tooling. The script uses interactive delegated PnP.PowerShell
authentication and retrieval cmdlets only. It never downloads content or mutates
SharePoint. Live execution requires separate owner approval.
#>
[CmdletBinding()]
param(
    [uri] $SiteUrl,
    [string] $ClientId,
    [string] $Tenant,
    [string] $OutputDirectory,
    [switch] $AllowRepositoryOutput,
    [datetimeoffset] $GeneratedAt = [datetimeoffset]::UtcNow
)

$script:EdnSchemaVersion = '1.0.0'
$script:EdnScriptVersion = '1.0.0'
$script:EdnOutputFiles = @(
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

function Read-EdnProperty {
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

function Test-EdnSecretName {
    param([Parameter(Mandatory)] [string] $Name)

    return $Name -match '(?i)^(authorization|cookie|credential|password|clientsecret|client_secret|access.?token|refresh.?token|id.?token|private.?key|certificate.?password)$'
}

function ConvertTo-EdnSafeValue {
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
    if ($InputObject -is [bool] -or $InputObject -is [byte] -or
        $InputObject -is [int16] -or $InputObject -is [int32] -or
        $InputObject -is [int64] -or $InputObject -is [decimal] -or
        $InputObject -is [double] -or $InputObject -is [single]) {
        return $InputObject
    }
    if ($InputObject -is [System.Collections.IDictionary]) {
        $safe = [ordered]@{}
        foreach ($key in @($InputObject.Keys | ForEach-Object { [string]$_ } | Sort-Object)) {
            if (-not (Test-EdnSecretName -Name $key)) {
                $safe[$key] = ConvertTo-EdnSafeValue -InputObject $InputObject[$key]
            }
        }
        return [pscustomobject]$safe
    }
    if ($InputObject -is [System.Collections.IEnumerable]) {
        return @($InputObject | ForEach-Object { ConvertTo-EdnSafeValue -InputObject $_ })
    }

    $safe = [ordered]@{}
    foreach ($property in @($InputObject.PSObject.Properties | Sort-Object Name)) {
        if (-not (Test-EdnSecretName -Name $property.Name)) {
            $safe[$property.Name] = ConvertTo-EdnSafeValue -InputObject $property.Value
        }
    }
    return [pscustomobject]$safe
}

function ConvertTo-EdnStableRecords {
    param(
        [AllowNull()] [object] $InputObject,
        [Parameter(Mandatory)] [string[]] $IdentityProperties
    )

    if ($null -eq $InputObject) { return @() }
    if ($InputObject -is [string] -or
        $InputObject -isnot [System.Collections.IEnumerable]) {
        throw 'Inventory records must be a collection.'
    }

    $seen = @{}
    $sortable = foreach ($record in @($InputObject)) {
        if ($null -eq $record -or $record -is [string]) {
            throw 'Inventory response contains a malformed record.'
        }
        $safe = ConvertTo-EdnSafeValue -InputObject $record
        $identity = @(
            foreach ($name in $IdentityProperties) {
                $value = Read-EdnProperty -InputObject $safe -Name $name
                if ($null -ne $value) { [string]$value }
            }
        ) -join '|'
        if (-not [string]::IsNullOrWhiteSpace($identity)) {
            if ($seen.ContainsKey($identity)) {
                throw "Duplicate inventory identity: $identity"
            }
            $seen[$identity] = $true
        }
        [pscustomobject]@{
            identity = $identity
            json = ($safe | ConvertTo-Json -Depth 30 -Compress)
            record = $safe
        }
    }
    return @($sortable | Sort-Object identity, json | ForEach-Object { $_.record })
}

function Resolve-EdnOutputPath {
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
    } else {
        [System.StringComparison]::Ordinal
    }
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $repoPrefix = $repoPath.TrimEnd($separator) + $separator
    $insideRepository = $fullPath.Equals($repoPath, $comparison) -or
        $fullPath.StartsWith($repoPrefix, $comparison)
    if ($insideRepository -and -not $AllowRepository) {
        throw 'OutputDirectory must be outside the repository. Use -AllowRepositoryOutput only after explicit approval.'
    }
    return $fullPath
}

function Protect-EdnMessage {
    param([AllowNull()] [string] $Message)

    if ([string]::IsNullOrWhiteSpace($Message)) { return 'No error message available.' }
    $safe = $Message -replace '(?i)Bearer\s+[A-Za-z0-9._~+/=-]+', 'Bearer [REDACTED]'
    $safe = $safe -replace '(?i)(client[_ -]?secret|password|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*\S+', '$1=[REDACTED]'
    if ($safe.Length -gt 500) { return $safe.Substring(0, 500) }
    return $safe
}

function Build-EdnEnvelope {
    param(
        [Parameter(Mandatory)] [string] $Site,
        [Parameter(Mandatory)] [datetimeoffset] $Timestamp,
        [AllowNull()] [object[]] $Records = @(),
        [string[]] $Warnings = @(),
        [string[]] $UnavailableSections = @()
    )

    return [ordered]@{
        schema_version = $script:EdnSchemaVersion
        script_version = $script:EdnScriptVersion
        generated_at_utc = $Timestamp.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
        site_url = $Site
        warnings = @($Warnings | Sort-Object -Unique)
        unavailable_sections = @($UnavailableSections | Sort-Object -Unique)
        records = @($Records)
    }
}

function Write-EdnJson {
    param(
        [Parameter(Mandatory)] [string] $Path,
        [Parameter(Mandatory)] [object] $Value
    )

    $json = (ConvertTo-EdnSafeValue -InputObject $Value) |
        ConvertTo-Json -Depth 50
    [System.IO.File]::WriteAllText(
        $Path,
        $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Get-EdnRoleRecords {
    param(
        [Parameter(Mandatory)] [object] $ScopeObject,
        [Parameter(Mandatory)] [string] $ScopeType,
        [Parameter(Mandatory)] [string] $ScopeId
    )

    $assignments = @(Get-PnPProperty -ClientObject $ScopeObject -Property RoleAssignments)
    foreach ($assignment in $assignments) {
        $member = Get-PnPProperty -ClientObject $assignment -Property Member
        $bindings = @(Get-PnPProperty -ClientObject $assignment -Property RoleDefinitionBindings)
        [ordered]@{
            scope_type = $ScopeType
            scope_id = $ScopeId
            has_unique_permissions = [bool](Read-EdnProperty $ScopeObject 'HasUniqueRoleAssignments')
            principal_id = Read-EdnProperty $member 'Id'
            principal_title = Read-EdnProperty $member 'Title'
            principal_type = [string](Read-EdnProperty $member 'PrincipalType')
            login_name = Read-EdnProperty $member 'LoginName'
            role_names = @($bindings | ForEach-Object { $_.Name } | Sort-Object -Unique)
        }
    }
}

function Export-EdnSharePointInventory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [uri] $ApprovedSiteUrl,
        [Parameter(Mandatory)] [string] $ApprovedClientId,
        [string] $ApprovedTenant,
        [Parameter(Mandatory)] [string] $ApprovedOutputDirectory,
        [switch] $RepositoryOutputApproved,
        [datetimeoffset] $Timestamp = [datetimeoffset]::UtcNow
    )

    if ($ApprovedSiteUrl.Scheme -ne 'https') { throw 'SiteUrl must use HTTPS.' }
    if ([string]::IsNullOrWhiteSpace($ApprovedClientId)) { throw 'ClientId is required.' }
    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $outputPath = Resolve-EdnOutputPath -Path $ApprovedOutputDirectory `
        -RepositoryRoot $repositoryRoot -AllowRepository:$RepositoryOutputApproved
    foreach ($name in $script:EdnOutputFiles) {
        if ([System.IO.File]::Exists([System.IO.Path]::Combine($outputPath, $name))) {
            throw "Refusing to overwrite existing inventory file: $name"
        }
    }

    Import-Module PnP.PowerShell -MinimumVersion 2.12.0 -ErrorAction Stop
    $connectArguments = @{
        Url = $ApprovedSiteUrl.AbsoluteUri
        ClientId = $ApprovedClientId
        Interactive = $true
        ReturnConnection = $true
        ErrorAction = 'Stop'
    }
    if (-not [string]::IsNullOrWhiteSpace($ApprovedTenant)) {
        $connectArguments['Tenant'] = $ApprovedTenant
    }
    $connection = Connect-PnPOnline @connectArguments

    $warnings = [System.Collections.Generic.List[string]]::new()
    $unavailable = [System.Collections.Generic.List[string]]::new()
    $errors = [System.Collections.Generic.List[object]]::new()
    $sites = [System.Collections.Generic.List[object]]::new()
    $listRecords = [System.Collections.Generic.List[object]]::new()
    $fields = [System.Collections.Generic.List[object]]::new()
    $contentTypes = [System.Collections.Generic.List[object]]::new()
    $views = [System.Collections.Generic.List[object]]::new()
    $permissions = [System.Collections.Generic.List[object]]::new()
    $automation = [System.Collections.Generic.List[object]]::new()
    $retention = [System.Collections.Generic.List[object]]::new()

    function CaptureFailure([string]$Section, [string]$Target, [System.Exception]$Exception) {
        $unavailable.Add($Section)
        $errors.Add([ordered]@{
            section = $Section
            target = $Target
            exception_type = $Exception.GetType().FullName
            message = Protect-EdnMessage -Message $Exception.Message
        })
    }

    $web = Get-PnPWeb -Connection $connection -Includes Title, Url, Id, WebTemplate,
        Configuration, Language, RegionalSettings, HasUniqueRoleAssignments,
        RoleAssignments -ErrorAction Stop
    $regional = Read-EdnProperty $web 'RegionalSettings'
    $timeZone = Read-EdnProperty $regional 'TimeZone'
    $owners = @()
    try {
        $owners = @(Get-PnPSiteCollectionAdmin -Connection $connection -ErrorAction Stop |
            ForEach-Object { $_.Title } | Sort-Object -Unique)
    } catch { CaptureFailure 'site_owners' $ApprovedSiteUrl.AbsoluteUri $_.Exception }

    $sharingCapability = $null
    try {
        $tenantSite = Get-PnPTenantSite -Identity $ApprovedSiteUrl.AbsoluteUri `
            -Detailed -Connection $connection -ErrorAction Stop
        $sharingCapability = [string](Read-EdnProperty $tenantSite 'SharingCapability')
    } catch { CaptureFailure 'site_sharing' $ApprovedSiteUrl.AbsoluteUri $_.Exception }

    $sites.Add([ordered]@{
        title = Read-EdnProperty $web 'Title'
        url = Read-EdnProperty $web 'Url'
        site_id = Read-EdnProperty $web 'Id'
        template = Read-EdnProperty $web 'WebTemplate'
        template_configuration = Read-EdnProperty $web 'Configuration'
        timezone_id = Read-EdnProperty $timeZone 'Id'
        timezone_description = Read-EdnProperty $timeZone 'Description'
        locale_id = Read-EdnProperty $regional 'LocaleId'
        language = Read-EdnProperty $web 'Language'
        owners = $owners
        sharing_capability = $sharingCapability
    })

    try {
        foreach ($record in @(Get-EdnRoleRecords -ScopeObject $web -ScopeType 'site' `
            -ScopeId ([string]$web.Id))) { $permissions.Add($record) }
    } catch { CaptureFailure 'site_permissions' ([string]$web.Id) $_.Exception }

    $lists = @(Get-PnPList -Connection $connection -Includes Id, Title, RootFolder,
        BaseType, BaseTemplate, ItemCount, Hidden, EnableVersioning,
        EnableMinorVersions, MajorVersionLimit, MajorWithMinorVersionsLimit,
        EnableModeration, ForceCheckout, EnableAttachments, HasUniqueRoleAssignments,
        RoleAssignments, ContentTypesEnabled, IrmEnabled, DefaultSensitivityLabelForLibrary,
        WorkflowAssociations -ErrorAction Stop)

    if ($lists.Count -eq 0) {
        throw 'List and library discovery returned zero records; refusing to write an incomplete inventory.'
    }

    foreach ($list in $lists) {
        $listId = ([guid]$list.Id).ToString('D').ToLowerInvariant()
        $rootFolder = Read-EdnProperty $list 'RootFolder'
        $rootName = Read-EdnProperty $rootFolder 'Name'
        $serverRelativeUrl = Read-EdnProperty $rootFolder 'ServerRelativeUrl'
        $listFields = @()
        try {
            $listFields = @(Get-PnPField -List $list.Id -Connection $connection `
                -ErrorAction Stop)
            foreach ($field in $listFields) {
                $fields.Add([ordered]@{
                    list_id = $listId
                    display_name = Read-EdnProperty $field 'Title'
                    internal_name = Read-EdnProperty $field 'InternalName'
                    field_id = Read-EdnProperty $field 'Id'
                    field_type = [string](Read-EdnProperty $field 'TypeAsString')
                    required = Read-EdnProperty $field 'Required'
                    hidden = Read-EdnProperty $field 'Hidden'
                    indexed = Read-EdnProperty $field 'Indexed'
                    lookup_list = Read-EdnProperty $field 'LookupList'
                    lookup_field = Read-EdnProperty $field 'LookupField'
                    choices = @((Read-EdnProperty $field 'Choices') | Sort-Object)
                    default_value = Read-EdnProperty $field 'DefaultValue'
                })
            }
        } catch { CaptureFailure 'fields' $listId $_.Exception }

        $indexedNames = @($listFields | Where-Object { $_.Indexed } |
            ForEach-Object { $_.InternalName } | Sort-Object -Unique)
        $listRecords.Add([ordered]@{
            list_id = $listId
            name = Read-EdnProperty $list 'Title'
            internal_name = $rootName
            base_type = [string](Read-EdnProperty $list 'BaseType')
            template = Read-EdnProperty $list 'BaseTemplate'
            url = $serverRelativeUrl
            item_count = Read-EdnProperty $list 'ItemCount'
            hidden = Read-EdnProperty $list 'Hidden'
            versioning_enabled = Read-EdnProperty $list 'EnableVersioning'
            minor_versions_enabled = Read-EdnProperty $list 'EnableMinorVersions'
            content_approval_enabled = Read-EdnProperty $list 'EnableModeration'
            checkout_required = Read-EdnProperty $list 'ForceCheckout'
            attachments_enabled = Read-EdnProperty $list 'EnableAttachments'
            indexed_columns = $indexedNames
            has_unique_permissions = Read-EdnProperty $list 'HasUniqueRoleAssignments'
        })

        try {
            foreach ($contentType in @(Get-PnPContentType -List $list.Id `
                -Connection $connection -ErrorAction Stop)) {
                $fieldLinks = @(Read-EdnProperty $contentType 'FieldLinks')
                $contentTypes.Add([ordered]@{
                    list_id = $listId
                    association_type = if ($list.BaseType -eq 'DocumentLibrary') { 'library' } else { 'list' }
                    content_type_id = [string](Read-EdnProperty $contentType 'Id')
                    name = Read-EdnProperty $contentType 'Name'
                    parent_id = [string](Read-EdnProperty (Read-EdnProperty $contentType 'Parent') 'Id')
                    attached_fields = @($fieldLinks | ForEach-Object {
                        [ordered]@{ id = [string]$_.Id; name = $_.Name }
                    } | Sort-Object id)
                })
            }
        } catch { CaptureFailure 'content_types' $listId $_.Exception }

        try {
            foreach ($view in @(Get-PnPView -List $list.Id -Connection $connection `
                -ErrorAction Stop)) {
                $views.Add([ordered]@{
                    list_id = $listId
                    view_id = Read-EdnProperty $view 'Id'
                    name = Read-EdnProperty $view 'Title'
                    url = Read-EdnProperty $view 'ServerRelativeUrl'
                    is_default = Read-EdnProperty $view 'DefaultView'
                    row_limit = Read-EdnProperty $view 'RowLimit'
                    query = Read-EdnProperty $view 'ViewQuery'
                    sort = Read-EdnProperty $view 'ViewData'
                    visible_fields = @((Read-EdnProperty $view 'ViewFields'))
                })
            }
        } catch { CaptureFailure 'views' $listId $_.Exception }

        try {
            foreach ($record in @(Get-EdnRoleRecords -ScopeObject $list `
                -ScopeType 'list' -ScopeId $listId)) { $permissions.Add($record) }
        } catch { CaptureFailure 'list_permissions' $listId $_.Exception }

        $customFormatter = Read-EdnProperty $list 'CustomFormatter'
        if (-not [string]::IsNullOrWhiteSpace([string]$customFormatter)) {
            $automation.Add([ordered]@{
                list_id = $listId; reference_type = 'list_formatting'
                reference_id = $listId; name = $list.Title; target = $serverRelativeUrl
            })
        }
        foreach ($workflow in @((Read-EdnProperty $list 'WorkflowAssociations'))) {
            $automation.Add([ordered]@{
                list_id = $listId; reference_type = 'workflow_association'
                reference_id = [string](Read-EdnProperty $workflow 'Id')
                name = Read-EdnProperty $workflow 'Name'; target = $serverRelativeUrl
            })
        }
        if ($null -ne (Get-Command Get-PnPWebhookSubscriptions -ErrorAction SilentlyContinue)) {
            try {
                foreach ($webhook in @(Get-PnPWebhookSubscriptions -List $list.Id `
                    -Connection $connection -ErrorAction Stop)) {
                    $automation.Add([ordered]@{
                        list_id = $listId; reference_type = 'webhook'
                        reference_id = [string](Read-EdnProperty $webhook 'Id')
                        name = $null; target = Read-EdnProperty $webhook 'NotificationUrl'
                    })
                }
            } catch { CaptureFailure 'webhooks' $listId $_.Exception }
        } else { $unavailable.Add('webhooks') }

        $retention.Add([ordered]@{
            scope_type = 'list'
            scope_id = $listId
            versioning_enabled = Read-EdnProperty $list 'EnableVersioning'
            minor_versions_enabled = Read-EdnProperty $list 'EnableMinorVersions'
            major_version_limit = Read-EdnProperty $list 'MajorVersionLimit'
            major_with_minor_versions_limit = Read-EdnProperty $list 'MajorWithMinorVersionsLimit'
            information_rights_management_enabled = Read-EdnProperty $list 'IrmEnabled'
            sensitivity_label_id = Read-EdnProperty $list 'DefaultSensitivityLabelForLibrary'
            retention_label = $null
            record_declaration = $null
            deletion_settings = $null
        })
    }

    $warnings.Add('Power Automate, Power Apps, external connector, Purview retention, and record declaration coverage is best-effort; unavailable metadata is not evidence of absence.')
    $unavailable.Add('power_automate_definitions')
    $unavailable.Add('power_apps_packages')
    $unavailable.Add('external_connector_configuration')
    $unavailable.Add('purview_policy_bodies')

    $recordSets = [ordered]@{
        'sites.json' = ConvertTo-EdnStableRecords $sites @('site_id', 'url')
        'lists-and-libraries.json' = ConvertTo-EdnStableRecords $listRecords @('list_id')
        'fields.json' = ConvertTo-EdnStableRecords $fields @('list_id', 'field_id')
        'content-types.json' = ConvertTo-EdnStableRecords $contentTypes @('list_id', 'content_type_id')
        'views.json' = ConvertTo-EdnStableRecords $views @('list_id', 'view_id')
        'permissions.json' = ConvertTo-EdnStableRecords $permissions @('scope_type', 'scope_id', 'principal_id')
        'automation-references.json' = ConvertTo-EdnStableRecords $automation @('list_id', 'reference_type', 'reference_id')
        'retention-metadata.json' = ConvertTo-EdnStableRecords $retention @('scope_type', 'scope_id')
        'discovery-errors.json' = ConvertTo-EdnStableRecords $errors @('section', 'target', 'exception_type')
    }

    [System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
    foreach ($entry in $recordSets.GetEnumerator()) {
        $envelope = Build-EdnEnvelope -Site $ApprovedSiteUrl.AbsoluteUri `
            -Timestamp $Timestamp -Records $entry.Value -Warnings $warnings `
            -UnavailableSections $unavailable
        Write-EdnJson -Path ([System.IO.Path]::Combine($outputPath, $entry.Key)) `
            -Value $envelope
    }
    $counts = [ordered]@{}
    foreach ($entry in $recordSets.GetEnumerator()) { $counts[$entry.Key] = @($entry.Value).Count }
    $summary = Build-EdnEnvelope -Site $ApprovedSiteUrl.AbsoluteUri `
        -Timestamp $Timestamp -Records @() -Warnings $warnings `
        -UnavailableSections $unavailable
    $summary['files'] = @($script:EdnOutputFiles | Sort-Object)
    $summary['record_counts'] = $counts
    Write-EdnJson -Path ([System.IO.Path]::Combine($outputPath, 'inventory-summary.json')) `
        -Value $summary

    return [pscustomobject]@{ OutputDirectory = $outputPath; RecordCounts = $counts }
}

if ($MyInvocation.InvocationName -ne '.') {
    if ($null -eq $SiteUrl -or [string]::IsNullOrWhiteSpace($ClientId) -or
        [string]::IsNullOrWhiteSpace($OutputDirectory)) {
        throw 'SiteUrl, ClientId, and OutputDirectory are required.'
    }
    Export-EdnSharePointInventory -ApprovedSiteUrl $SiteUrl `
        -ApprovedClientId $ClientId -ApprovedTenant $Tenant `
        -ApprovedOutputDirectory $OutputDirectory `
        -RepositoryOutputApproved:$AllowRepositoryOutput -Timestamp $GeneratedAt
}
