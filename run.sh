#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/pip install -q -r requirements.txt
.venv/bin/python scripts/init_db.py

address="${WORKLOG_ADDRESS:-127.0.0.1}"
port="${WORKLOG_PORT:-8501}"
args=(-c gunicorn.conf.py app:app)

if [[ "${1:-}" == "bg" || "${1:-}" == "--background" ]]; then
  nohup .venv/bin/gunicorn "${args[@]}" >worklog.log 2>&1 &
  echo $! >worklog.pid
  echo "工作日志已启动：http://${address}:${port}（PID $(cat worklog.pid)）"
else
  exec .venv/bin/gunicorn "${args[@]}"
fi
