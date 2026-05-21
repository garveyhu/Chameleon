#!/usr/bin/env bash
# run-local.sh —— 本地全栈拉起（PG + Redis + backend + ui）
#
# 参数协议：
#   不传参 = 全量 build + up（base + code + ui）
#   传参   = 只 rebuild 指定子集 + up
#
# 例：
#   ./run-local.sh                    # 全部
#   ./run-local.sh code               # 只 rebuild code
#   ./run-local.sh code ui            # code + ui

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONTAINERS_DIR="${ROOT}/docker/containers"

# 1. .env 兜底
if [ ! -f "${CONTAINERS_DIR}/.env" ]; then
  echo "[run] 缺 ${CONTAINERS_DIR}/.env，从 .env.example 复制"
  cp "${CONTAINERS_DIR}/.env.example" "${CONTAINERS_DIR}/.env"
  echo ""
  echo "⚠️  请编辑 docker/containers/.env 设置 PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY"
  echo "   生成密钥：python3 -c \"import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())\""
  exit 1
fi

# 2. 运行时挂载目录（脚本自动建，避免 docker 用 root 创建）
mkdir -p "${CONTAINERS_DIR}/data/pg" \
         "${CONTAINERS_DIR}/data/redis" \
         "${CONTAINERS_DIR}/data/resources" \
         "${CONTAINERS_DIR}/data/logs"

# 3. build（透传参数）
"${SCRIPT_DIR}/build-images.sh" "$@"

# 4. compose down → up
cd "${CONTAINERS_DIR}"
echo "[run] compose down (keep volumes)"
docker compose down --remove-orphans || true

echo "[run] compose up -d"
docker compose up -d --remove-orphans

# 5. 等主容器健康
echo "[run] 等 chameleon-backend healthy..."
deadline=$(( $(date +%s) + 90 ))
while [ $(date +%s) -lt "$deadline" ]; do
  status=$(docker inspect -f '{{.State.Health.Status}}' chameleon-backend 2>/dev/null || echo "starting")
  if [ "${status}" = "healthy" ]; then
    break
  fi
  sleep 2
done

# 6. banner
. "${CONTAINERS_DIR}/.env"
cat <<EOF

────────────────────────────────────────────
  Chameleon 本地实例已就绪
────────────────────────────────────────────
  UI            http://localhost:${UI_HOST_PORT:-6006}
  Backend API   http://localhost:${BACKEND_HOST_PORT:-7009}/docs
  Postgres      127.0.0.1:${PG_HOST_PORT:-5432}  (user=${PG_USER:-chameleon})
  Redis         127.0.0.1:${REDIS_HOST_PORT:-6379}

  首次启动会自动 seed admin，登录凭据在 data/logs/initial-admin-credentials.txt
────────────────────────────────────────────
EOF
