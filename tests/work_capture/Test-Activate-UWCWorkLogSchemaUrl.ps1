#Requires -Version 7.2

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$activationScript = Join-Path `
    $PSScriptRoot `
    "..\..\installer\Activate-UWCWorkLogSchema.ps1"
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    $activationScript,
    [ref]$tokens,
    [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    throw "Activation script parse failed: $($parseErrors -join '; ')"
}

$functionAst = $ast.Find(
    {
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq "Test-EquivalentSharePointSiteUrl"
    },
    $true
)
if ($null -eq $functionAst) {
    throw "Test-EquivalentSharePointSiteUrl was not found."
}

. ([scriptblock]::Create($functionAst.Extent.Text))

$expected = "https://edn123.sharepoint.com/sites/EDNSystems"
$caseEquivalent = "https://edn123.sharepoint.com/sites/ednsystems"
$differentSite = "https://edn123.sharepoint.com/sites/AnotherSite"

if (-not (Test-EquivalentSharePointSiteUrl $expected $caseEquivalent)) {
    throw "Equivalent SharePoint site URL casing was rejected."
}
if (Test-EquivalentSharePointSiteUrl $expected $differentSite) {
    throw "A genuinely different SharePoint site path was accepted."
}

Write-Output "SharePoint site URL identity regression: PASS"
