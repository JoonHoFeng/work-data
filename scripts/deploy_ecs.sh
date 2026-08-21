#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${WORKLOG_HOST:-}"
SSH_USER="${WORKLOG_USER:-root}"
PORT="${WORKLOG_PORT:-8501}"
ADDRESS="${WORKLOG_ADDRESS:-127.0.0.1}"
PASSWORD="${WORKLOG_PASSWORD:-}"
KEY="${WORKLOG_SSH_KEY:-}"
REMOTE_DIR=/opt/worklog

if [ -z "$HOST" ]; then
  echo "请设置 WORKLOG_HOST=服务器IP"
  exit 1
fi
if [[ "$PASSWORD" == *$'\n'* ]]; then
  echo "WORKLOG_PASSWORD 不能包含换行"
  exit 1
fi

ssh_args=(-o StrictHostKeyChecking=accept-new)
if [ -n "$KEY" ]; then ssh_args+=(-i "$KEY"); fi
remote="${SSH_USER}@${HOST}"
password_b64="$(printf %s "$PASSWORD" | base64 | tr -d '\n')"

ssh "${ssh_args[@]}" "$remote" "mkdir -p '$REMOTE_DIR'"
rsync -az --delete -e "ssh ${ssh_args[*]}" \
  --exclude .git --exclude .venv --exclude __pycache__ \
  --exclude 'data/*.db*' --exclude 'reports/*.db' \
  --exclude 'worklog.env' --exclude '*.log' --exclude '*.pid' \
  "$ROOT/" "$remote:$REMOTE_DIR/"

ssh "${ssh_args[@]}" "$remote" bash -s -- "$PORT" "$ADDRESS" "$password_b64" <<'REMOTE_SCRIPT'
set -euo pipefail
port="$1"
address="$2"
password="$(printf %s "$3" | base64 -d)"
cd /opt/worklog

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
elif command -v yum >/dev/null 2>&1; then
  yum install -y python3 python3-pip >/dev/null
fi

id worklog >/dev/null 2>&1 || useradd --system --home /opt/worklog --shell /usr/sbin/nologin worklog
mkdir -p data reports
chown -R worklog:worklog /opt/worklog

if [ ! -x .venv/bin/python ]; then
  runuser -u worklog -- python3 -m venv .venv
fi
runuser -u worklog -- .venv/bin/pip install -q -U pip
runuser -u worklog -- .venv/bin/pip install -q -r requirements.txt
runuser -u worklog -- .venv/bin/python scripts/init_db.py

secret="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
escaped="${password//\\/\\\\}"
escaped="${escaped//\"/\\\"}"
{
  printf 'WORKLOG_ADDRESS=%s\n' "$address"
  printf 'WORKLOG_PORT=%s\n' "$port"
  printf 'WORKLOG_WORKERS=1\nWORKLOG_THREADS=2\n'
  printf 'WORKLOG_SECRET_KEY=%s\n' "$secret"
  printf 'WORKLOG_PASSWORD="%s"\n' "$escaped"
} >worklog.env
chmod 600 worklog.env
chown worklog:worklog worklog.env

cp deploy/worklog.service /etc/systemd/system/worklog.service
systemctl daemon-reload
systemctl enable --now worklog
systemctl restart worklog
systemctl --no-pager --full status worklog
REMOTE_SCRIPT

echo "部署完成。服务监听 ${ADDRESS}:${PORT}"
if [ "$ADDRESS" = "127.0.0.1" ]; then
  echo "请通过已有 Nginx/Caddy 反向代理访问（推荐）。"
else
  echo "直连地址：http://${HOST}:${PORT}；请限制安全组来源并尽快配置 HTTPS。"
fi
