#!/usr/bin/env sh
# chameleon-base 容器入口（主 backend 容器跑它）
#
# 前置条件（由 init 容器准备）：
#   /app/.venv       ← venv-init cp 自 chameleon-venv:/export/.venv
#   /app/chameleon-* ← code-init cp 自 chameleon-code:/export/
#   /app/migrations  ← code-init cp（同上）
#   /app/alembic.ini ← code-init cp（同上）
#
# 行为：
#   migrate    —— 只跑 alembic upgrade head（一次性容器）
#   serve      —— alembic upgrade head + 起 uvicorn（默认）
#   exec <cmd> —— 透传任意命令
#   <other>    —— 透传给 chameleon CLI（init-admin / db ...）

set -eu

VENV_BIN=/app/.venv/bin
cd /app

run_migration() {
  if [ ! -f /app/alembic.ini ]; then
    echo "[entrypoint] /app/alembic.ini 不存在 —— code volume 未正确挂载？" >&2
    exit 1
  fi
  echo "[entrypoint] alembic upgrade head..."
  "${VENV_BIN}/alembic" upgrade head
}

case "${1:-serve}" in
  migrate)
    run_migration
    ;;
  serve)
    run_migration
    echo "[entrypoint] starting uvicorn on 0.0.0.0:${CHAMELEON_PORT:-7009}..."
    exec "${VENV_BIN}/uvicorn" chameleon.app.main:app \
      --host 0.0.0.0 \
      --port "${CHAMELEON_PORT:-7009}" \
      --workers "${CHAMELEON_WORKERS:-2}" \
      --log-level "${CHAMELEON_LOG_LEVEL:-info}" \
      --proxy-headers
    ;;
  exec)
    shift
    exec "$@"
    ;;
  *)
    exec "${VENV_BIN}/chameleon" "$@"
    ;;
esac
