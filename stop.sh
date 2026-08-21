#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f worklog.pid ]; then
  echo "没有找到 worklog.pid"
  exit 0
fi

pid="$(cat worklog.pid)"
if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "已停止工作日志（PID $pid）"
else
  echo "进程已不存在"
fi
rm -f worklog.pid
