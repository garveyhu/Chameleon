#!/usr/bin/env bash
# backend/run.sh —— 本地开发起后端（uv workspace 多包架构 + uvicorn 热更新）
#
# 重构后后端是 10 个 chameleon-* 包的 uv workspace。plain `uvicorn --reload` 从 backend/
# 起会连 .venv / logs 一起监听 → 重启风暴；而从单个包目录起又监听不到跨包改动。本脚本把
# --reload-dir 显式指到每个包的 src（+ config），跨包改任意 .py / config json 都能热更新。
#
# 用法：
#   ./run.sh            dev（默认）：--reload 热更新，单 worker，127.0.0.1:7009，监听全部 chameleon-*/src + config
#   ./run.sh prod       生产式：多 worker，0.0.0.0，无 reload，--proxy-headers
#
# 环境变量（覆盖默认）：
#   HOST / PORT / LOG_LEVEL / WORKERS   默认 127.0.0.1 / 7009 / info / 2
#   SKIP_MIGRATE=1                      跳过启动前 alembic upgrade head
#   NO_RELOAD=1                         dev 模式也关掉 reload

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MODE="${1:-dev}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-7009}"
LOG_LEVEL="${LOG_LEVEL:-info}"
APP="chameleon.app.main:app"
UVICORN="${ROOT}/.venv/bin/uvicorn"
ALEMBIC="${ROOT}/.venv/bin/alembic"

# venv 缺失 → 先同步 workspace 依赖
if [ ! -x "$UVICORN" ]; then
  echo "[run] 未发现 ${UVICORN}，执行 uv sync 同步 workspace 依赖 ..."
  uv sync
fi

# 启动前迁移（幂等：已是 head 则 no-op）。SKIP_MIGRATE=1 跳过
if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
  echo "[run] alembic upgrade head ..."
  "$ALEMBIC" upgrade head
fi

ARGS=("$APP" --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL")

case "$MODE" in
  prod | serve)
    WORKERS="${WORKERS:-2}"
    ARGS+=(--workers "$WORKERS" --proxy-headers)
    echo "[run] serve  ${HOST}:${PORT}  workers=${WORKERS}  (no reload)"
    ;;
  dev)
    if [ "${NO_RELOAD:-0}" != "1" ]; then
      # 只监听各包 src（*.py）+ config（*.json），避开 .venv / logs / *_cache 的噪声。
      # 包 src 分三层深度：flat（chameleon-core/src）、一层嵌套（providers/local/src、
      # agents/qwen_chat/src）、两层嵌套（agents/examples/echo/src），三段 glob 全覆盖。
      ARGS+=(--reload --reload-include "*.json")
      n=0
      for src in "${ROOT}"/chameleon-*/src \
                 "${ROOT}"/chameleon-*/*/src \
                 "${ROOT}"/chameleon-*/*/*/src; do
        [ -d "$src" ] && { ARGS+=(--reload-dir "$src"); n=$((n + 1)); }
      done
      [ -d "${ROOT}/config" ] && ARGS+=(--reload-dir "${ROOT}/config")
      echo "[run] dev  ${HOST}:${PORT}  reload=on  监听 ${n} 个包 + config"
    else
      echo "[run] dev  ${HOST}:${PORT}  reload=off"
    fi
    ;;
  *)
    echo "[run] 未知模式：${MODE}（可用：dev / prod）" >&2
    exit 1
    ;;
esac

exec "$UVICORN" "${ARGS[@]}"
