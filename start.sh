#!/usr/bin/env bash
# Сверка договоров поставки — запуск одной командой (macOS / Linux)
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python; [ -x "$PY" ] || PY=.venv/Scripts/python
"$PY" -m pip install -q -r backend/requirements.txt
(cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)
echo "Открой http://localhost:8000  (API: http://localhost:8000/docs)"
exec "$PY" -m uvicorn app.main:app --app-dir backend --port 8000
