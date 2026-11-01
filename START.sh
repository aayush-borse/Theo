#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="$(command -v python3.11 || command -v python3)"
if [[ ! -x .venv/bin/python ]]; then "$PYTHON_BIN" -m venv .venv; fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
if grep -q '^THEO_JWT_SECRET=replace-with' .env; then
  SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i.bak "s/^THEO_JWT_SECRET=.*/THEO_JWT_SECRET=${SECRET}/" .env && rm -f .env.bak
fi
echo '[THEO] Installing backend dependencies...'
.venv/bin/python -m pip install --disable-pip-version-check -r backend/requirements.txt
export PYTHONPATH="$PWD/backend"
echo '[THEO] Open http://127.0.0.1:8000'
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
