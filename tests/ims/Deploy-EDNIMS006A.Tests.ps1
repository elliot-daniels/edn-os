$scriptPath = Join-Path $PSScriptRoot '..' '..' 'installer' 'Deploy-EDNIMS006A.ps1'
. $scriptPath
$productionManifestPath = Join-Path $PSScriptRoot '..' '..' 'config' 'ims-006a-fields.json'

function New-SyntheticManifestFile {
    param([string] $Path, [object[]] $Fields)
    [pscustomobject]@{
        schema_version = '1.0.0'
        increment = 'IMS-006A'
        mode = 'additive_optional_fields_only'
        site_identity = 'explicit-at-runtime'
        fields = $Fields
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function New-SyntheticField {
    param([string] $Name = 'IMSExample', [string] $Type = 'Text')
    return [pscustomobject]@{
        list = 'Synthetic Projects'
        list_id = '11111111-1111-1111-1111-111111111111'
        display_name = 'IMS example'
        internal_name = $Name
        type = $Type
        indexed_recommended = $false
    }
}

Describe 'IMS-006A manifest safety' {
    It 'accepts the versioned production design manifest as additive and optional' {
        $manifest = Read-Edn006AManifest -Path $productionManifestPath
        @($manifest.fields).Count | Should BeGreaterThan 0
        @($manifest.fields | Where-Object { $_.PSObject.Properties.Name -contains 'required' -and $_.required }).Count | Should Be 0
        @($manifest.fields | Where-Object { $_.PSObject.Properties.Name -contains 'lookup_target' }).Count | Should Be 0
    }

    It 'rejects a required field' {
        $field = New-SyntheticField
        $field | Add-Member -NotePropertyName required -NotePropertyValue $true
        $path = Join-Path $TestDrive 'required.json'
        New-SyntheticManifestFile $path @($field)
        { Read-Edn006AManifest $path } | Should Throw 'IMS-006A refuses required fields.'
    }

    It 'rejects lookups and unsupported field types' {
        $lookup = New-SyntheticField
        $lookup | Add-Member -NotePropertyName lookup_target -NotePropertyValue 'Future List'
        $lookupPath = Join-Path $TestDrive 'lookup.json'
        New-SyntheticManifestFile $lookupPath @($lookup)
        { Read-Edn006AManifest $lookupPath } | Should Throw 'IMS-006A refuses lookup fields.'

        $unsupportedPath = Join-Path $TestDrive 'unsupported.json'
        New-SyntheticManifestFile $unsupportedPath @((New-SyntheticField -Type 'Calculated'))
        { Read-Edn006AManifest $unsupportedPath } | Should Throw 'Unsupported field type: Calculated'
    }

    It 'rejects duplicate and unsafe internal names' {
        $duplicatePath = Join-Path $TestDrive 'duplicate.json'
        New-SyntheticManifestFile $duplicatePath @((New-SyntheticField), (New-SyntheticField))
        { Read-Edn006AManifest $duplicatePath } | Should Throw 'Duplicate manifest field: 11111111-1111-1111-1111-111111111111|imsexample'

        $unsafePath = Join-Path $TestDrive 'unsafe.json'
        New-SyntheticManifestFile $unsafePath @((New-SyntheticField -Name 'Title'))
        { Read-Edn006AManifest $unsafePath } | Should Throw 'Unsafe internal name: Title'
    }
}

Describe 'IMS-006A field compatibility and idempotence' {
    It 'classifies missing, compatible and incompatible definitions' {
        $desired = New-SyntheticField
        (Test-Edn006AFieldCompatibility $desired $null) | Should Be 'missing'
        $compatible = [pscustomobject]@{ TypeAsString = 'Text'; Required = $false }
        (Test-Edn006AFieldCompatibility $desired $compatible) | Should Be 'compatible'
        $wrongType = [pscustomobject]@{ TypeAsString = 'Note'; Required = $false }
        (Test-Edn006AFieldCompatibility $desired $wrongType) | Should Be 'incompatible'
        $required = [pscustomobject]@{ TypeAsString = 'Text'; Required = $true }
        (Test-Edn006AFieldCompatibility $desired $required) | Should Be 'incompatible'
    }

    It 'requires exact choice definitions for compatibility' {
        $desired = New-SyntheticField -Type 'Choice'
        $desired | Add-Member -NotePropertyName choices -NotePropertyValue @('A','B')
        (Test-Edn006AFieldCompatibility $desired ([pscustomobject]@{TypeAsString='Choice';Required=$false;Choices=@('B','A')})) | Should Be 'compatible'
        (Test-Edn006AFieldCompatibility $desired ([pscustomobject]@{TypeAsString='Choice';Required=$false;Choices=@('A','C')})) | Should Be 'incompatible'
    }

    It 'does not create a compatible field on a second deployment' {
        $manifest = [pscustomobject]@{ fields = @((New-SyntheticField)) }
        $plan = @([pscustomobject]@{list='Synthetic Projects';list_id='11111111-1111-1111-1111-111111111111';internal_name='IMSExample';type='Text';state='compatible';action='already_compliant'})
        Mock Add-PnPField { throw 'must not be called' }
        $result = Invoke-Edn006AApply -Manifest $manifest -Plan $plan
        $result[0].action | Should Be 'already_compliant'
    }

    It 'creates only a missing optional field' {
        $manifest = [pscustomobject]@{ fields = @((New-SyntheticField)) }
        $plan = @([pscustomobject]@{list='Synthetic Projects';list_id='11111111-1111-1111-1111-111111111111';internal_name='IMSExample';type='Text';state='missing';action='create'})
        Mock Add-PnPField { [pscustomobject]@{} }
        $result = Invoke-Edn006AApply -Manifest $manifest -Plan $plan
        $result[0].action | Should Be 'created'
        Assert-MockCalled Add-PnPField -Times 1
    }

    It 'refuses all creation if any incompatible field exists' {
        $manifest = [pscustomobject]@{ fields = @((New-SyntheticField)) }
        $plan = @([pscustomobject]@{state='incompatible';internal_name='IMSExample'})
        Mock Add-PnPField { throw 'must not be called' }
        { Invoke-Edn006AApply -Manifest $manifest -Plan $plan } | Should Throw 'Apply refused because incompatible fields exist.'
    }
}

Describe 'IMS-006A output and secrets safety' {
    It 'does not overwrite a report' {
        $path = Join-Path $TestDrive 'report.json'
        Set-Content -LiteralPath $path -Value '{}'
        { Write-Edn006AReport -Path $path -Value @{} } | Should Throw "Output already exists: $path"
    }

    It 'redacts secret and bearer-shaped values from errors' {
        $safe = Protect-Edn006AMessage 'password=synthetic-secret Bearer abc.def.ghi'
        $safe | Should Not Match 'synthetic-secret'
        $safe | Should Not Match 'abc\.def\.ghi'
    }
}

Describe 'IMS-006A static mutation boundary' {
    It 'parses without errors and allows only Add-PnPField as a tenant mutation' {
        $tokens = $null
        $errors = $null
        $ast = [Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
        $errors | Should BeNullOrEmpty
        $names = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]}, $true) | ForEach-Object {$_.GetCommandName()} | Where-Object {$_})
        $mutations = @($names | Where-Object { $_ -match '^(Add|Set|Update|Remove|New)-PnP' })
        $mutations.Count | Should Be 1
        $mutations[0] | Should Be 'Add-PnPField'
        ($names -contains 'Remove-PnPField') | Should Be $false
        ($names -contains 'Set-PnPField') | Should Be $false
        ($names -contains 'Add-PnPList') | Should Be $false
    }

    It 'uses interactive authentication and has no unattended credentials' {
        $raw = Get-Content -Raw -LiteralPath $scriptPath
        $raw | Should Match 'Connect-PnPOnline'
        $raw | Should Match 'Interactive'
        $raw | Should Not Match '(?i)-ClientSecret|-CertificatePath|-Thumbprint'
    }

    It 'contains no destructive rollback command or item mutation' {
        $raw = Get-Content -Raw -LiteralPath $scriptPath
        $raw | Should Not Match 'Remove-PnPField|Remove-PnPList|Set-PnPListItem|Add-PnPListItem|Remove-PnPListItem'
    }
}
