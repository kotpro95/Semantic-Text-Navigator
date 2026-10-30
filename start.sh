#!/usr/bin/env bash
# Сверка договоров поставки — запуск одной командой (macOS / Linux / Git Bash)
set -euo pipefail
cd "$(dirname "$0")"

# python3 на macOS/Linux; на Windows python3 бывает заглушкой Microsoft Store — тогда берём python
SYS_PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>/dev/null; then SYS_PY=$c; break; fi
done
[ -n "$SYS_PY" ] || { echo "Нужен Python 3.10+ в PATH" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Нужен Node.js 18+ (npm) в PATH" >&2; exit 1; }

[ -d .venv ] || "$SYS_PY" -m venv .venv
PY=.venv/bin/python; [ -x "$PY" ] || PY=.venv/Scripts/python
"$PY" -m pip install -q --disable-pip-version-check -r backend/requirements.txt
(cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build)
echo "Открой http://localhost:8000  (API: http://localhost:8000/docs)"
exec "$PY" -m uvicorn app.main:app --app-dir backend --port 8000
