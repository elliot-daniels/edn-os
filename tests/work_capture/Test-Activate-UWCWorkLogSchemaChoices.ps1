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

$functionNames = @(
    "Stop-Activation",
    "Get-UwcFieldSchemaDocument",
    "Get-UwcChoiceValuesFromSchema",
    "Get-UwcLookupIdentityFromSchema",
    "Assert-ExistingField"
)
foreach ($functionName in $functionNames) {
    $functionAst = $ast.Find(
        {
            param($node)
            $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $functionName
        },
        $true
    )
    if ($null -eq $functionAst) {
        throw "$functionName was not found."
    }
    . ([scriptblock]::Create($functionAst.Extent.Text))
}

$compatibleRateCode = [pscustomobject]@{
    InternalName = "RateCode"
    TypeAsString = "Choice"
    SchemaXml = @"
<Field Type="Choice" Name="RateCode">
  <CHOICES>
    <CHOICE>APEX-95</CHOICE>
    <CHOICE>Scheduled Night-135</CHOICE>
  </CHOICES>
</Field>
"@
}
$compatibleMap = @{ RateCode = $compatibleRateCode }
Assert-ExistingField `
    $compatibleMap `
    "RateCode" `
    "Choice" `
    -RequiredChoices @("APEX-95", "Scheduled Night-135")

$missingChoice = [pscustomobject]@{
    InternalName = "RateCode"
    TypeAsString = "Choice"
    SchemaXml = @"
<Field Type="Choice" Name="RateCode">
  <CHOICES><CHOICE>APEX-95</CHOICE></CHOICES>
</Field>
"@
}
$missingChoiceFailedClosed = $false
try {
    Assert-ExistingField `
        @{ RateCode = $missingChoice } `
        "RateCode" `
        "Choice" `
        -RequiredChoices @("APEX-95", "Scheduled Night-135")
}
catch {
    if ($_.Exception.Message -like "*missing approved value 'Scheduled Night-135'*") {
        $missingChoiceFailedClosed = $true
    }
    else {
        throw
    }
}
if (-not $missingChoiceFailedClosed) {
    throw "Missing required choice validation was bypassed."
}

$emptyChoices = [pscustomobject]@{
    InternalName = "RateCode"
    TypeAsString = "Choice"
    SchemaXml = '<Field Type="Choice" Name="RateCode"><CHOICES /></Field>'
}
$emptyChoiceFailedClosed = $false
try {
    Assert-ExistingField `
        @{ RateCode = $emptyChoices } `
        "RateCode" `
        "Choice" `
        -RequiredChoices @("APEX-95")
}
catch {
    if ($_.Exception.Message -like "*exposes no CHOICE values*") {
        $emptyChoiceFailedClosed = $true
    }
    else {
        throw
    }
}
if (-not $emptyChoiceFailedClosed) {
    throw "Empty choice-schema validation was bypassed."
}

Write-Output "SharePoint choice schema regression: PASS"
