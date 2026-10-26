# Starts the FastAPI backend on http://127.0.0.1:8000 (API docs at /docs).
$ErrorActionPreference = "Stop"
$Backend = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "backend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Host "Run .\setup.ps1 first." -ForegroundColor Red; exit 1 }
Set-Location $Backend
& $Py -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
