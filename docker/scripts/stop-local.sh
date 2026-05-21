#!/usr/bin/env bash
# stop-local.sh —— 停掉本地 compose
#
# 用法：
#   ./stop-local.sh         # 停容器，保留 data/
#   ./stop-local.sh -v      # 停容器并清空 data/（容器 named volume + bind mount data/）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONTAINERS_DIR="${ROOT}/docker/containers"

cd "${CONTAINERS_DIR}"

if [ "${1:-}" = "-v" ]; then
  echo "[stop] compose down + 清 data/"
  docker compose down --volumes --remove-orphans
  rm -rf "${CONTAINERS_DIR}/data"
else
  echo "[stop] compose down"
  docker compose down --remove-orphans
fi
