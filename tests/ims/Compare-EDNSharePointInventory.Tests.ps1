$scriptPath = Join-Path $PSScriptRoot '..' '..' 'installer' 'Compare-EDNSharePointInventory.ps1'
. $scriptPath

function Write-SyntheticJson {
    param([string] $Path, [object] $Value)
    $json = $Value | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText(
        $Path, $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Write-SyntheticInventory {
    param(
        [string] $Directory,
        [string[]] $Unavailable = @(),
        [string] $SkipFile,
        [string] $SchemaVersion = '1.0.0',
        [switch] $IncludeSecret
    )

    [System.IO.Directory]::CreateDirectory($Directory) | Out-Null
    $lists = @(
        [ordered]@{ list_id = '11111111-1111-1111-1111-111111111111'; name = 'Projects'; internal_name = 'Projects'; base_type = 'GenericList'; url = '/sites/edn/Lists/Projects'; versioning_enabled = $true; minor_versions_enabled = $false; has_unique_permissions = $false },
        [ordered]@{ list_id = '22222222-2222-2222-2222-222222222222'; name = 'Project Register'; internal_name = 'ProjectRegister'; base_type = 'GenericList'; url = '/sites/edn/Lists/ProjectRegister'; versioning_enabled = $true; minor_versions_enabled = $false; has_unique_permissions = $false },
        [ordered]@{ list_id = '33333333-3333-3333-3333-333333333333'; name = 'Actions'; internal_name = 'Actions'; base_type = 'GenericList'; url = '/sites/edn/Lists/Actions'; versioning_enabled = $true; minor_versions_enabled = $false; has_unique_permissions = $false },
        [ordered]@{ list_id = '44444444-4444-4444-4444-444444444444'; name = 'Assets'; internal_name = 'Assets'; base_type = 'GenericList'; url = '/sites/edn/Lists/Assets'; versioning_enabled = $false; minor_versions_enabled = $false; has_unique_permissions = $true },
        [ordered]@{ list_id = '55555555-5555-5555-5555-555555555555'; name = 'Risks and Opportunities'; internal_name = 'RisksAndOpportunities'; base_type = 'GenericList'; url = '/sites/edn/Lists/Risks'; versioning_enabled = $true; minor_versions_enabled = $false; has_unique_permissions = $false },
        [ordered]@{ list_id = '66666666-6666-6666-6666-666666666666'; name = 'Social Committee'; internal_name = 'SocialCommittee'; base_type = 'GenericList'; url = '/sites/edn/Lists/SocialCommittee'; versioning_enabled = $true; minor_versions_enabled = $false; has_unique_permissions = $false }
    )
    if ($IncludeSecret) { $lists[0]['password'] = 'synthetic-secret-value' }
    $fields = @(
        [ordered]@{ list_id = $lists[0].list_id; field_id = 'a0000000-0000-0000-0000-000000000001'; internal_name = 'ProjectCode'; field_type = 'Text' },
        [ordered]@{ list_id = $lists[0].list_id; field_id = 'a0000000-0000-0000-0000-000000000002'; internal_name = 'ClientId'; field_type = 'Lookup' },
        [ordered]@{ list_id = $lists[1].list_id; field_id = 'b0000000-0000-0000-0000-000000000001'; internal_name = 'ProjectCode'; field_type = 'Text' },
        [ordered]@{ list_id = $lists[1].list_id; field_id = 'b0000000-0000-0000-0000-000000000002'; internal_name = 'ClientId'; field_type = 'Lookup' },
        [ordered]@{ list_id = $lists[3].list_id; field_id = 'd0000000-0000-0000-0000-000000000001'; internal_name = 'Classification'; field_type = 'Choice' },
        [ordered]@{ list_id = $lists[3].list_id; field_id = 'd0000000-0000-0000-0000-000000000002'; internal_name = 'AssetOwner'; field_type = 'User' }
    )
    $contentTypes = @(
        [ordered]@{ list_id = $lists[0].list_id; content_type_id = '0x0101'; name = 'Project' }
    )
    $views = @(
        [ordered]@{ list_id = $lists[0].list_id; view_id = 'e0000000-0000-0000-0000-000000000001'; name = 'Active Projects' }
    )
    $permissions = @(
        [ordered]@{ scope_type = 'list'; scope_id = $lists[3].list_id; principal_id = 7; principal_title = 'Asset Owners'; role_names = @('Edit'); has_unique_permissions = $true }
    )
    $automation = @(
        [ordered]@{ list_id = $lists[4].list_id; reference_type = 'workflow_association'; reference_id = 'f0000000-0000-0000-0000-000000000001' }
    )
    $retention = @(
        foreach ($list in @($lists | Where-Object { $_.list_id -ne $lists[3].list_id })) {
            [ordered]@{ scope_type = 'list'; scope_id = $list.list_id; versioning_enabled = $list.versioning_enabled; retention_label = 'Synthetic Retention'; record_declaration = $false }
        }
    )
    $recordsByFile = [ordered]@{
        'inventory-summary.json' = @()
        'sites.json' = @([ordered]@{ site_id = '00000000-0000-0000-0000-000000000001'; title = 'Synthetic EDN'; url = 'https://example.sharepoint.com/sites/edn' })
        'lists-and-libraries.json' = $lists
        'fields.json' = $fields
        'content-types.json' = $contentTypes
        'views.json' = $views
        'permissions.json' = $permissions
        'automation-references.json' = $automation
        'retention-metadata.json' = $retention
        'discovery-errors.json' = @()
    }
    foreach ($entry in $recordsByFile.GetEnumerator()) {
        if ($entry.Key -eq $SkipFile) { continue }
        $envelope = [ordered]@{
            schema_version = $SchemaVersion
            script_version = '1.0.0'
            generated_at_utc = '2026-08-07T00:00:00.000Z'
            site_url = 'https://example.sharepoint.com/sites/edn'
            warnings = @()
            unavailable_sections = @($Unavailable)
            records = @($entry.Value)
        }
        Write-SyntheticJson (Join-Path $Directory $entry.Key) $envelope
    }
}

Describe 'EDN SharePoint inventory comparison validation' {
    It 'accepts the supported complete schema' {
        $inventory = Join-Path $TestDrive 'inventory-valid'
        Write-SyntheticInventory $inventory

        $result = Read-GapInventory $inventory

        $result.Documents.Count | Should Be 10
        $result.Quality.Count | Should Be 0
    }

    It 'rejects an unsupported schema version' {
        $inventory = Join-Path $TestDrive 'inventory-schema'
        Write-SyntheticInventory $inventory -SchemaVersion '9.9.9'

        { Read-GapInventory $inventory } |
            Should Throw 'Unsupported inventory schema in inventory-summary.json: 9.9.9'
    }

    It 'refuses an incomplete inventory by default' {
        $inventory = Join-Path $TestDrive 'inventory-incomplete'
        Write-SyntheticInventory $inventory -SkipFile 'retention-metadata.json'

        { Read-GapInventory $inventory } |
            Should Throw 'Incomplete inventory: missing retention-metadata.json'
    }

    It 'records incomplete inventory when explicitly allowed' {
        $inventory = Join-Path $TestDrive 'inventory-incomplete-allowed'
        Write-SyntheticInventory $inventory -SkipFile 'retention-metadata.json'

        $result = Read-GapInventory $inventory -AllowIncomplete

        @($result.Quality | Where-Object { $_.code -eq 'missing_file' }).Count |
            Should Be 1
    }
}

Describe 'EDN SharePoint gap mapping behavior' {
    It 'detects duplicate lists using material field overlap' {
        $inventory = Join-Path $TestDrive 'inventory-duplicates'
        Write-SyntheticInventory $inventory
        $loaded = Read-GapInventory $inventory

        $duplicates = Build-GapDuplicates `
            (Get-GapRecords $loaded 'lists-and-libraries.json') `
            (Get-GapRecords $loaded 'fields.json')

        $projectDuplicate = @($duplicates | Where-Object {
            $_.left_name -eq 'Projects' -and $_.right_name -eq 'Project Register'
        })
        $projectDuplicate.Count | Should Be 1
        $projectDuplicate[0].field_overlap | Should Be 1
    }

    It 'classifies authoritative, extension, creation, decision, and out-of-scope cases' {
        $inventory = Join-Path $TestDrive 'inventory-classification'
        $output = Join-Path $TestDrive 'gap-classification'
        Write-SyntheticInventory $inventory

        Compare-EdnSharePointInventory $inventory $output `
            -RepositoryOutputApproved -Timestamp ([datetimeoffset]'2026-08-07T01:00:00Z') | Out-Null
        $report = Get-Content -Raw (Join-Path $output 'object-recommendations.json') |
            ConvertFrom-Json

        (@($report.records | Where-Object { $_.name -eq 'Actions' }))[0].classification |
            Should Be 'Reuse unchanged'
        (@($report.records | Where-Object { $_.name -eq 'Assets' }))[0].classification |
            Should Be 'Extend existing'
        (@($report.records | Where-Object { $_.name -eq 'Controlled Documents' }))[0].classification |
            Should Be 'Create new'
        (@($report.records | Where-Object { $_.name -eq 'Projects' }))[0].classification |
            Should Be 'Needs owner decision'
        (@($report.records | Where-Object { $_.name -eq 'Social Committee' }))[0].classification |
            Should Be 'Out of IMS scope'
    }

    It 'flags permission, versioning, retention, and automation risks' {
        $inventory = Join-Path $TestDrive 'inventory-risks'
        $output = Join-Path $TestDrive 'gap-risks'
        Write-SyntheticInventory $inventory

        Compare-EdnSharePointInventory $inventory $output `
            -RepositoryOutputApproved -Timestamp ([datetimeoffset]'2026-08-07T01:00:00Z') | Out-Null
        $report = Get-Content -Raw (Join-Path $output 'object-recommendations.json') |
            ConvertFrom-Json
        $assets = (@($report.records | Where-Object { $_.name -eq 'Assets' }))[0]
        $risks = (@($report.records | Where-Object { $_.name -eq 'Risks and Opportunities' }))[0]

        ($assets.risks -join '|') | Should Match 'Permissions require'
        ($assets.risks -join '|') | Should Match 'Versioning is observed disabled'
        ($assets.risks -join '|') | Should Match 'No list retention metadata'
        $risks.automation_dependencies.Count | Should Be 1
    }

    It 'treats unavailable retention as unknown rather than absent' {
        $inventory = Join-Path $TestDrive 'inventory-unavailable'
        $output = Join-Path $TestDrive 'gap-unavailable'
        Write-SyntheticInventory $inventory -Unavailable @('purview_policy_bodies')

        Compare-EdnSharePointInventory $inventory $output `
            -RepositoryOutputApproved -Timestamp ([datetimeoffset]'2026-08-07T01:00:00Z') | Out-Null
        $report = Get-Content -Raw (Join-Path $output 'object-recommendations.json') |
            ConvertFrom-Json
        $assets = (@($report.records | Where-Object { $_.name -eq 'Assets' }))[0]

        ($assets.unresolved_questions -join '|') | Should Match 'unknown because discovery was unavailable'
        ($assets.risks -join '|') | Should Not Match 'No list retention metadata'
    }

    It 'produces deterministic JSON and Markdown for fixed input and timestamp' {
        $inventory = Join-Path $TestDrive 'inventory-deterministic'
        $first = Join-Path $TestDrive 'gap-first'
        $second = Join-Path $TestDrive 'gap-second'
        Write-SyntheticInventory $inventory
        $timestamp = [datetimeoffset]'2026-08-07T01:00:00Z'

        Compare-EdnSharePointInventory $inventory $first `
            -RepositoryOutputApproved -Timestamp $timestamp | Out-Null
        Compare-EdnSharePointInventory $inventory $second `
            -RepositoryOutputApproved -Timestamp $timestamp | Out-Null

        foreach ($name in $script:GapOutputFiles) {
            [Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $first $name))) |
                Should Be ([Convert]::ToBase64String([System.IO.File]::ReadAllBytes((Join-Path $second $name))))
        }
    }

    It 'excludes secret-like input from generated reports' {
        $inventory = Join-Path $TestDrive 'inventory-secret'
        $output = Join-Path $TestDrive 'gap-secret'
        Write-SyntheticInventory $inventory -IncludeSecret

        Compare-EdnSharePointInventory $inventory $output `
            -RepositoryOutputApproved -Timestamp ([datetimeoffset]'2026-08-07T01:00:00Z') | Out-Null
        $combined = @($script:GapOutputFiles | ForEach-Object {
            Get-Content -Raw (Join-Path $output $_)
        }) -join "`n"

        $combined | Should Not Match 'synthetic-secret-value'
        $combined | Should Not Match '"password"'
    }
}

Describe 'EDN SharePoint gap mapping safety' {
    It 'refuses repository output by default' {
        $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
        { Resolve-GapOutputPath (Join-Path $repositoryRoot 'GapAssessment') $repositoryRoot } |
            Should Throw 'OutputDirectory must be outside the repository.'
    }

    It 'contains no network, authentication, SharePoint, or Git commands' {
        $tokens = $null
        $parseErrors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $scriptPath, [ref]$tokens, [ref]$parseErrors
        )
        $parseErrors | Should BeNullOrEmpty
        $names = @($ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.CommandAst]
        }, $true) | ForEach-Object { $_.GetCommandName() } | Where-Object { $_ })
        $prohibited = @($names | Where-Object {
            $_ -match 'PnP|MgGraph|RestMethod|WebRequest|WebSocket|^git$|Credential|Connect-|Disconnect-'
        })

        $prohibited | Should BeNullOrEmpty
    }
}
