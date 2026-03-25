#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/azureuser/project10}"
BACKEND_DIR="$APP_DIR/backend"
SOCKET_PATH="${SOCKET_PATH:-$BACKEND_DIR/project10.sock}"

cd "$BACKEND_DIR"

if [ -f "$BACKEND_DIR/.env" ]; then
  echo "Found $BACKEND_DIR/.env (Django will load it via python-dotenv)."
fi

source "$BACKEND_DIR/venv/bin/activate"

gunicorn --workers 2 --timeout 300 \
  --bind "unix:$SOCKET_PATH" \
  auto_invest.wsgi:application
