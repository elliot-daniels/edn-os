$scriptPath = Join-Path $PSScriptRoot '..' '..' 'installer' 'Export-EDNSharePointInventory.ps1'
$fixturePath = Join-Path $PSScriptRoot 'fixtures' 'inventory-records.json'
$duplicateFixturePath = Join-Path $PSScriptRoot 'fixtures' 'duplicate-records.json'

. $scriptPath

Describe 'EDN SharePoint inventory normalization' {
    It 'sorts records deterministically and preserves missing properties' {
        $fixture = Get-Content -Raw -LiteralPath $fixturePath | ConvertFrom-Json
        $records = ConvertTo-EdnStableRecords -InputObject $fixture.records `
            -IdentityProperties @('list_id')

        $records.Count | Should Be 2
        $records[0].name | Should Be 'Actions'
        ($records[0].PSObject.Properties.Name -contains 'item_count') | Should Be $false
        $records[1].name | Should Be 'Projects'
    }

    It 'emits byte-identical JSON for identical normalized input' {
        $fixture = Get-Content -Raw -LiteralPath $fixturePath | ConvertFrom-Json
        $records = ConvertTo-EdnStableRecords $fixture.records @('list_id')
        $timestamp = [datetimeoffset]'2026-08-06T01:02:03Z'
        $envelope = Build-EdnEnvelope -Site 'https://example.sharepoint.com/sites/edn' `
            -Timestamp $timestamp -Records $records -Warnings @('z', 'a', 'a') `
            -UnavailableSections @('views', 'automation')
        $first = Join-Path $TestDrive 'first.json'
        $second = Join-Path $TestDrive 'second.json'

        Write-EdnJson -Path $first -Value $envelope
        Write-EdnJson -Path $second -Value $envelope

        [System.IO.File]::ReadAllBytes($first) |
            Should Be ([System.IO.File]::ReadAllBytes($second))
        (Get-Content -Raw $first) | Should Match '2026-08-06T01:02:03.000Z'
    }

    It 'rejects duplicate stable IDs' {
        $fixture = Get-Content -Raw -LiteralPath $duplicateFixturePath |
            ConvertFrom-Json
        { ConvertTo-EdnStableRecords $fixture.records @('list_id') } |
            Should Throw 'Duplicate inventory identity: 11111111-1111-1111-1111-111111111111'
    }

    It 'rejects malformed scalar responses' {
        { ConvertTo-EdnStableRecords 'malformed' @('id') } |
            Should Throw 'Inventory records must be a collection.'
    }

    It 'removes secret properties recursively and redacts bearer-shaped values' {
        $fixture = Get-Content -Raw -LiteralPath $fixturePath | ConvertFrom-Json
        $safe = ConvertTo-EdnSafeValue $fixture
        $json = $safe | ConvertTo-Json -Depth 20

        $json | Should Not Match 'synthetic-password'
        $json | Should Not Match 'synthetic\.token\.value'
        $json | Should Not Match '"password"'
        $json | Should Not Match '"authorization"'
        $json | Should Match 'classification'
    }
}

Describe 'EDN SharePoint inventory output path safety' {
    It 'refuses repository output by default' {
        $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
        $inside = Join-Path $repositoryRoot 'SharePointInventory'

        { Resolve-EdnOutputPath -Path $inside -RepositoryRoot $repositoryRoot } |
            Should Throw 'OutputDirectory must be outside the repository. Use -AllowRepositoryOutput only after explicit approval.'
    }

    It 'accepts an external explicit output path' {
        $repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..' '..'))
        $result = Resolve-EdnOutputPath -Path $TestDrive -RepositoryRoot $repositoryRoot

        $result | Should Be ([System.IO.Path]::GetFullPath($TestDrive))
    }

    It 'requires a nonblank output path' {
        { Resolve-EdnOutputPath -Path ' ' -RepositoryRoot $PSScriptRoot } |
            Should Throw 'OutputDirectory must be explicitly supplied.'
    }
}

Describe 'EDN SharePoint inventory static read-only safety' {
    It 'contains no prohibited tenant mutation commands' {
        $tokens = $null
        $parseErrors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $scriptPath, [ref]$tokens, [ref]$parseErrors
        )
        $parseErrors | Should BeNullOrEmpty

        $commands = $ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.CommandAst]
        }, $true)
        $names = @($commands | ForEach-Object { $_.GetCommandName() } |
            Where-Object { $null -ne $_ })
        $prohibited = @($names | Where-Object {
            $_ -match '^(Add|Set|Update|Remove|New)-' -or
            $_ -eq 'Invoke-PnPProvisioningTemplate'
        })

        $prohibited | Should BeNullOrEmpty
    }

    It 'contains no web request commands' {
        $tokens = $null
        $parseErrors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile(
            $scriptPath, [ref]$tokens, [ref]$parseErrors
        )
        $requestCommands = $ast.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.CommandAst] -and
            $node.GetCommandName() -in @('Invoke-RestMethod', 'Invoke-WebRequest')
        }, $true)

        $requestCommands | Should BeNullOrEmpty
    }

    It 'uses only interactive delegated authentication' {
        $raw = Get-Content -Raw -LiteralPath $scriptPath
        $raw | Should Match 'Connect-PnPOnline'
        $raw | Should Match 'Interactive'
        $raw | Should Not Match '(?i)-ClientSecret|-CertificatePath|-Thumbprint'
    }
}
