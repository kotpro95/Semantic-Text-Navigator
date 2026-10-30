# Сверка договоров поставки — запуск одной командой (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r backend\requirements.txt
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install --no-audit --no-fund }
npm run build
Pop-Location
Write-Host "Открой http://localhost:8000  (API: http://localhost:8000/docs)"
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000
