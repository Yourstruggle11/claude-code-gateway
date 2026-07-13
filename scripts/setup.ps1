[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3.10 or newer was not found. Install Python and try again."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not create .venv. Review the error above and verify the venv module is installed."
    }
}

& ".venv\Scripts\python.exe" -c 'import sys; print(f"Using Python {sys.version.split()[0]}"); sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) {
    throw ".venv uses Python older than 3.10. Remove .venv and rerun setup with a newer Python."
}

& ".venv\Scripts\python.exe" -m pip install --editable .
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Review the pip error above."
}
& ".venv\Scripts\claude-gateway.exe" setup
exit $LASTEXITCODE
