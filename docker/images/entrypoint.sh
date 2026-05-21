#!/usr/bin/env sh
# chameleon-code 容器入口
#
# 行为：
#   migrate    —— 跑 alembic upgrade head 后退出（适合一次性迁移容器）
#   serve      —— 跑 alembic upgrade head + 起 uvicorn（默认）
#   exec <cmd> —— 透传任意命令（调试用）

set -eu

run_migration() {
  echo "[entrypoint] alembic upgrade head..."
  cd /app
  /app/.venv/bin/alembic upgrade head
}

case "${1:-serve}" in
  migrate)
    run_migration
    ;;
  serve)
    run_migration
    echo "[entrypoint] starting uvicorn on 0.0.0.0:${CHAMELEON_PORT:-7009}..."
    exec /app/.venv/bin/uvicorn chameleon.app.main:app \
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
    # 兼容直接传命令（如 chameleon init-admin）
    exec /app/.venv/bin/chameleon "$@"
    ;;
esac
