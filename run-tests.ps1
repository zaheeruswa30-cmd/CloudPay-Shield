# Runs the backend test suite. Each test uses its own temporary database;
# backend\cloudpay_shield.db is never opened or changed.
$ErrorActionPreference = "Stop"
$Backend = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "backend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Host "Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
Push-Location $Backend
try {
    & $Py -m pytest
    $code = $LASTEXITCODE
} finally { Pop-Location }
Push-Location (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "frontend")
try {
    if (Test-Path "node_modules") { Write-Host "`nChecking the frontend builds..." -ForegroundColor Cyan; npm run build }
} finally { Pop-Location }
exit $code
