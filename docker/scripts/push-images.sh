#!/usr/bin/env bash
# push-images.sh —— 推到内网 registry（支持多架构）
#
# 参数协议：
#   不传参 = push 全部（base / code / ui）
#   传参   = 只 push 指定的子集
#
# 凭据：docker/scripts/.registry.env（gitignored）
#
# 注意：本脚本不自动创建 buildx builder——尊重用户当前激活的（可能配过 HTTP registry）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IMAGES_DIR="${ROOT}/docker/images"

if [ ! -f "${SCRIPT_DIR}/.registry.env" ]; then
  echo "[push] 缺 ${SCRIPT_DIR}/.registry.env，从 .registry.env.example 复制并填写仓库凭据" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
. "${IMAGES_DIR}/.env"
. "${SCRIPT_DIR}/.registry.env"
set +a

: "${REGISTRY_URL:?REGISTRY_URL 未设置}"
: "${REGISTRY_USER:?REGISTRY_USER 未设置}"
: "${REGISTRY_PASSWORD:?REGISTRY_PASSWORD 未设置}"
: "${REGISTRY_NAMESPACE:?REGISTRY_NAMESPACE 未设置}"

PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

echo "[push] login ${REGISTRY_URL}"
echo "${REGISTRY_PASSWORD}" | docker login "${REGISTRY_URL}" -u "${REGISTRY_USER}" --password-stdin

ALL_TARGETS=(base code ui)
TARGETS=("${@:-${ALL_TARGETS[@]}}")
if [ "${#TARGETS[@]}" -eq 0 ]; then
  TARGETS=("${ALL_TARGETS[@]}")
fi

push_one() {
  local name=$1 tag=$2 dockerfile=$3 extra_args=("${@:4}")
  local remote="${REGISTRY_URL}/${REGISTRY_NAMESPACE}/chameleon-${name}:${tag}"
  echo "[push] ${name} → ${remote}"
  docker buildx build \
    --platform "${PLATFORMS}" \
    -t "${remote}" \
    -f "${IMAGES_DIR}/${dockerfile}" \
    --push \
    ${extra_args[@]+"${extra_args[@]}"} \
    "${ROOT}"
}

for t in "${TARGETS[@]}"; do
  case "$t" in
    base)
      push_one base "${CHAMELEON_BASE_TAG}" Dockerfile.base
      ;;
    code)
      push_one code "${CHAMELEON_CODE_TAG}" Dockerfile.code \
        --build-arg BASE_IMAGE="${REGISTRY_URL}/${REGISTRY_NAMESPACE}/chameleon-base" \
        --build-arg BASE_TAG="${CHAMELEON_BASE_TAG}"
      ;;
    ui)
      push_one ui "${CHAMELEON_UI_TAG}" Dockerfile.ui
      ;;
    *)
      echo "[push] 未知 target: $t" >&2; exit 1
      ;;
  esac
done

echo "[push] done"
