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
        $node.Name -ceq "Get-UwcWebhookMetadataSnapshot"
    },
    $true
)
if ($null -eq $functionAst) {
    throw "Get-UwcWebhookMetadataSnapshot was not found."
}
. ([scriptblock]::Create($functionAst.Extent.Text))

$emptyMetadata = @(Get-UwcWebhookMetadataSnapshot -Webhooks @())
if ($emptyMetadata.Count -ne 0) {
    throw "Zero webhooks did not produce a valid empty metadata snapshot."
}

$webhooks = @(
    [pscustomobject]@{
        Id = "11111111-1111-1111-1111-111111111111"
        ExpirationDateTime = [DateTimeOffset]"2026-09-01T00:00:00Z"
    },
    [pscustomobject]@{
        Id = "22222222-2222-2222-2222-222222222222"
        ExpirationDateTime = [DateTimeOffset]"2026-09-02T00:00:00Z"
    }
)
$metadata = @(Get-UwcWebhookMetadataSnapshot -Webhooks $webhooks)
if ($metadata.Count -ne 2) {
    throw "Well-formed webhooks were not retained as metadata."
}
foreach ($item in $metadata) {
    $propertyNames = @($item.Keys)
    if (
        $propertyNames.Count -ne 2 -or
        $propertyNames -cnotcontains "Id" -or
        $propertyNames -cnotcontains "ExpirationUtc"
    ) {
        throw "Webhook snapshot contains non-approved or secret-bearing metadata."
    }
}

$malformedFailedClosed = $false
try {
    [void](Get-UwcWebhookMetadataSnapshot -Webhooks @(
        [pscustomobject]@{
            Id = "not-a-guid"
            ExpirationDateTime = [DateTimeOffset]"2026-09-01T00:00:00Z"
        }
    ))
}
catch {
    if ($_.Exception.Message -like "*invalid identity*") {
        $malformedFailedClosed = $true
    }
    else {
        throw
    }
}
if (-not $malformedFailedClosed) {
    throw "Malformed webhook validation was bypassed."
}

$duplicateFailedClosed = $false
try {
    [void](Get-UwcWebhookMetadataSnapshot -Webhooks @(
        [pscustomobject]@{
            Id = "33333333-3333-3333-3333-333333333333"
            ExpirationDateTime = [DateTimeOffset]"2026-09-01T00:00:00Z"
        },
        [pscustomobject]@{
            Id = "33333333-3333-3333-3333-333333333333"
            ExpirationDateTime = [DateTimeOffset]"2026-09-02T00:00:00Z"
        }
    ))
}
catch {
    if ($_.Exception.Message -like "*duplicate identity*") {
        $duplicateFailedClosed = $true
    }
    else {
        throw
    }
}
if (-not $duplicateFailedClosed) {
    throw "Ambiguous webhook validation was bypassed."
}

Write-Output "SharePoint webhook metadata regression: PASS"
