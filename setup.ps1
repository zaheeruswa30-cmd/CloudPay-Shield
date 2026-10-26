# CloudPay Shield - first-time setup (safe to run again).
# Never deletes or resets backend\cloudpay_shield.db. Seeding only runs on an empty database.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "Missing: $cmd. $hint" -ForegroundColor Red
        exit 1
    }
}
Need "python" "Install Python 3.12+ from python.org and tick 'Add python.exe to PATH'."
Need "node" "Install Node.js 22 LTS from nodejs.org."
Need "npm" "npm comes with Node.js; reopen VS Code after installing Node."

Write-Host "Python: $(python --version)"
Write-Host "Node:   $(node --version)"

Write-Host "`n[1/4] Python virtual environment" -ForegroundColor Cyan
$Venv = Join-Path $Backend ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
} else {
    Write-Host "Already exists: $Venv"
}

Write-Host "`n[2/4] Backend packages" -ForegroundColor Cyan
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed. See the messages above." }

Write-Host "`n[3/4] Local secrets and demo data" -ForegroundColor Cyan
Push-Location $Backend
try {
    # config.py creates backend\.env with random secrets if they are missing.
    # Optional: the backend also creates tables and demo data on its first start.
    # seed.py does nothing if the database already has users.
    & $Py seed.py
    if ($LASTEXITCODE -ne 0) { Write-Host "seed.py reported a problem; the backend will try again on first start." -ForegroundColor Yellow }
} finally { Pop-Location }

Write-Host "`n[4/4] Frontend packages" -ForegroundColor Cyan
Push-Location $Frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
} finally { Pop-Location }

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host "Next: run .\start-backend.ps1 in one terminal and .\start-frontend.ps1 in another."
Write-Host "Then open http://localhost:5173"
