# Starts the React dashboard on http://localhost:5173 (needs the backend running).
$ErrorActionPreference = "Stop"
$Frontend = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "frontend"
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { Write-Host "Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
Set-Location $Frontend
npm run dev
