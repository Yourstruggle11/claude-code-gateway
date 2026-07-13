[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)][string[]] $ClaudeArgs)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
$Gateway = "$RootDir\.venv\Scripts\claude-gateway.exe"
if (-not (Test-Path $Gateway)) {
    throw "Gateway is not installed. Run .\scripts\setup.ps1 first."
}
& $Gateway claude @ClaudeArgs
exit $LASTEXITCODE
