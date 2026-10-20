#!/bin/sh
set -eu

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
uvicorn_pid=$!

cleanup() {
  kill "$uvicorn_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

nginx -g 'daemon off;'
