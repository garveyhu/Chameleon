#!/usr/bin/env bash
# build-images.sh —— 本地 build Chameleon 镜像
#
# 参数协议：
#   不传参 = build 全部（base / code / ui）
#   传参   = 只 build 指定的子集
#
# 例：
#   ./build-images.sh              # base + code + ui
#   ./build-images.sh code         # 只 code
#   ./build-images.sh code ui      # code + ui

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IMAGES_DIR="${ROOT}/docker/images"

if [ ! -f "${IMAGES_DIR}/.env" ]; then
  echo "[build] 未找到 ${IMAGES_DIR}/.env，从 .env.example 复制"
  cp "${IMAGES_DIR}/.env.example" "${IMAGES_DIR}/.env"
fi

# shellcheck disable=SC1091
set -a
. "${IMAGES_DIR}/.env"
set +a

REGISTRY_PREFIX="${REGISTRY_PREFIX:-chameleon}"

ALL_TARGETS=(base code ui)
TARGETS=("${@:-${ALL_TARGETS[@]}}")
if [ "${#TARGETS[@]}" -eq 0 ]; then
  TARGETS=("${ALL_TARGETS[@]}")
fi

build_base() {
  local img="chameleon/chameleon-base:${CHAMELEON_BASE_TAG}"
  if docker image inspect "${img}" >/dev/null 2>&1; then
    echo "[build] base 已存在 (${img})，跳过；如需重建删除镜像后重跑"
    return
  fi
  echo "[build] base → ${img}"
  docker build \
    -t "${img}" \
    -f "${IMAGES_DIR}/Dockerfile.base" \
    "${ROOT}"
}

build_code() {
  local img="chameleon/chameleon-code:${CHAMELEON_CODE_TAG}"
  echo "[build] code → ${img}"
  docker build \
    --build-arg BASE_IMAGE=chameleon/chameleon-base \
    --build-arg BASE_TAG="${CHAMELEON_BASE_TAG}" \
    -t "${img}" \
    -f "${IMAGES_DIR}/Dockerfile.code" \
    "${ROOT}"
}

build_ui() {
  local img="chameleon/chameleon-ui:${CHAMELEON_UI_TAG}"
  echo "[build] ui → ${img}"
  docker build \
    -t "${img}" \
    -f "${IMAGES_DIR}/Dockerfile.ui" \
    "${ROOT}"
}

for t in "${TARGETS[@]}"; do
  case "$t" in
    base) build_base ;;
    code) build_code ;;
    ui)   build_ui   ;;
    *)    echo "[build] 未知 target: $t（可选: base / code / ui）" >&2; exit 1 ;;
  esac
done

echo "[build] done"
