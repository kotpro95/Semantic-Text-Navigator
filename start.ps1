# Contract check prototype - one-command start (Windows PowerShell 5.1+)
# ASCII only: PS 5.1 reads BOM-less scripts in the ANSI code page, Cyrillic would break parsing.
# No $ErrorActionPreference = "Stop": in PS 5.1 any stderr line of a native command
# (e.g. a pip notice) aborts the script. Exit codes are checked explicitly instead.
Set-Location $PSScriptRoot

function Step($what, [scriptblock]$cmd) {
    Write-Host "==> $what"
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $what (exit code $LASTEXITCODE)" -ForegroundColor Red; exit 1 }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Python 3.10+ is required in PATH" -ForegroundColor Red; exit 1 }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Write-Host "Node.js 18+ (npm) is required in PATH" -ForegroundColor Red; exit 1 }

if (-not (Test-Path .venv)) { Step "Creating .venv" { python -m venv .venv } }
Step "Installing Python dependencies" { .\.venv\Scripts\python -m pip install -q --disable-pip-version-check -r backend\requirements.txt }
Push-Location frontend
if (-not (Test-Path node_modules)) { Step "Installing frontend dependencies" { npm install --no-audit --no-fund } }
Step "Building frontend" { npm run build }
Pop-Location
Write-Host "Open http://localhost:8000  (API docs: http://localhost:8000/docs)"
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
