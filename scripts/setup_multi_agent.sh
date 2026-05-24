#!/usr/bin/env bash
# Chameleon 4 agent 并行开发环境一键启动
#
# 跑这个脚本前：
#   - 当前位于主 worktree 根目录（含 backend/、frontend/）
#   - main 分支已 push 到 origin（脚本基于当前 HEAD 创建 4 个 branch）
#   - 已装：git / uv / yarn / psql (postgres@15+) / redis-cli
#
# 跑这个脚本会：
#   1. 创建 .worktrees/{workflow-engine,rag-deepen,billing-gateway,ui-deepen}
#   2. 每个 worktree 独立 branch（feat/v1.1-{name}）
#   3. 每个后端 worktree 跑 uv sync（共享 uv cache，~10 秒）
#   4. 创建 3 个独立 PG DB（chameleon_a / _b / _c；D 共享主 DB）
#   5. 复制并参数化 backend/config/.env（端口 / DB / Redis prefix）
#   6. 打印 4 个目录 + 启动指令
#
# 跑完之后：开 4 个终端 cd 进各自 worktree 启 claude
#
# 不做的事（用户自己）：
#   - 修改各 worktree 的 model.json / agents.yaml 凭据（按需）
#   - 4 个 worktree alembic upgrade head + demo seed（启动 backend 时跑）
#   - 启动 frontend dev server（按需，D 必启，其他选启）

set -euo pipefail

# ── 颜色 ────────────────────────────────────────────────
RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
BLUE='\033[34m'
RESET='\033[0m'

info()  { echo -e "${BLUE}→${RESET} $*"; }
ok()    { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}!${RESET} $*"; }
fail()  { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── 先决检查 ───────────────────────────────────────────
[[ -d backend && -d frontend && -d .git ]] \
  || fail "请在 Chameleon 主仓库根目录跑（找不到 backend/frontend/.git）"

command -v git >/dev/null || fail "git 没装"
command -v uv >/dev/null  || fail "uv 没装（brew install uv）"
command -v psql >/dev/null || warn "psql 没装；跳过 DB 创建步骤（手动建）"

main_repo=$(git rev-parse --show-toplevel)
cd "$main_repo"

# ── 4 个 agent 定义 ────────────────────────────────────
AGENTS=(
  "workflow-engine|feat/v1.1-workflow-engine|A|Workflow 引擎深化|8001|6007|chameleon_a|cm:a:"
  "rag-deepen|feat/v1.1-rag-deepen|B|RAG 检索深化|8002|6008|chameleon_b|cm:b:"
  "billing-gateway|feat/v1.1-billing-gateway|C|计费 + Gateway 深化|8003|6009|chameleon_c|cm:c:"
  "ui-deepen|feat/v1.1-ui-deepen|D|前端体验深化|8004|6010|chameleon|cm:"
)

# ── 1. 创建 worktree + branch ───────────────────────────
mkdir -p .worktrees
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r dir branch tag title port_be port_fe db redis <<< "$entry"
  path=".worktrees/$dir"
  if [[ -d "$path" ]]; then
    warn "worktree $path 已存在，跳过 git worktree add（继续装依赖）"
  else
    info "创建 worktree: $path (branch $branch)"
    git worktree add "$path" -b "$branch" 2>&1 | sed 's/^/    /'
  fi
done
ok "4 个 worktree 就位"

# ── 2. 每个 worktree 跑 uv sync ─────────────────────────
for entry in "${AGENTS[@]}"; do
  IFS='|' read -r dir branch tag title port_be port_fe db redis <<< "$entry"
  if [[ "$dir" == "ui-deepen" ]]; then
    info "[$tag] $dir 是前端 agent，跳过 uv sync（D 不写后端代码）"
    continue
  fi
  path=".worktrees/$dir"
  info "[$tag] $path: uv sync"
  (cd "$path/backend" && uv sync 2>&1 | tail -3 | sed 's/^/    /')
done
ok "后端依赖装好"

# ── 3. 创建独立 PG DB（A / B / C 各自；D 共享主 DB）──────
if command -v psql >/dev/null; then
  for entry in "${AGENTS[@]}"; do
    IFS='|' read -r dir branch tag title port_be port_fe db redis <<< "$entry"
    if [[ "$db" == "chameleon" ]]; then
      info "[$tag] $dir 共享主 DB chameleon，跳过 createdb"
      continue
    fi
    if psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "$db"; then
      warn "[$tag] DB $db 已存在，跳过 createdb（如要重置：dropdb $db && 重跑）"
    else
      info "[$tag] createdb $db"
      createdb "$db" 2>&1 | sed 's/^/    /' || warn "createdb $db 失败（手动建）"
    fi
  done
  ok "PG DB 就位"
else
  warn "psql 没装，手动创建 chameleon_a / _b / _c 三个 DB"
fi

# ── 4. 每个 worktree 准备 .env（复制主 .env + sed 改端口/DB/Redis）──────
main_env="backend/config/.env"
if [[ ! -f "$main_env" ]]; then
  warn "主 worktree 没有 $main_env；跳过 .env 复制（用户自己配每个 worktree）"
else
  for entry in "${AGENTS[@]}"; do
    IFS='|' read -r dir branch tag title port_be port_fe db redis <<< "$entry"
    if [[ "$dir" == "ui-deepen" ]]; then
      info "[$tag] $dir 不需要后端 .env"
      continue
    fi
    target=".worktrees/$dir/backend/config/.env"
    if [[ -f "$target" ]]; then
      warn "[$tag] $target 已存在，跳过覆盖（手动检查端口/DB/Redis prefix）"
      continue
    fi
    info "[$tag] cp $main_env → $target（端口 $port_be / DB $db / Redis $redis）"
    mkdir -p "$(dirname "$target")"
    cp "$main_env" "$target"
    # sed 替换端口 / DB / Redis prefix（按你 .env 实际 key 命名调整）
    # 假定 .env 用 DATABASE_URL=postgresql+asyncpg://.../chameleon
    sed -i '' "s|/chameleon$|/$db|g; s|/chameleon |/$db |g" "$target" 2>/dev/null || true
    # 加 / 改 SERVER_PORT
    if grep -q "^SERVER_PORT=" "$target"; then
      sed -i '' "s/^SERVER_PORT=.*/SERVER_PORT=$port_be/" "$target"
    else
      echo "SERVER_PORT=$port_be" >> "$target"
    fi
    # Redis prefix（如 .env 有 REDIS_KEY_PREFIX 或自行加）
    if grep -q "^REDIS_KEY_PREFIX=" "$target"; then
      sed -i '' "s|^REDIS_KEY_PREFIX=.*|REDIS_KEY_PREFIX=$redis|" "$target"
    else
      echo "REDIS_KEY_PREFIX=$redis" >> "$target"
    fi
  done
  ok ".env 文件参数化完成（请自行检查 DATABASE_URL / API_KEY 等敏感字段）"
fi

# ── 5. 打印启动指南 ─────────────────────────────────────
cat <<'EOF'

═════════════════════════════════════════════════════════════════
  4 Agent 并行开发环境已就绪
═════════════════════════════════════════════════════════════════

下一步：开 4 个终端窗口，分别 cd 进各 worktree 启动 claude code。

EOF

for entry in "${AGENTS[@]}"; do
  IFS='|' read -r dir branch tag title port_be port_fe db redis <<< "$entry"
  cat <<EOF
─── Agent $tag · $title ────────────────────────────────────
    cd $main_repo/.worktrees/$dir
    claude
    （首条指令告诉它：读 docs/plans/2026-05-24-v1.1-multi-agent-plan.md § 3 Agent $tag）

    资源：backend port $port_be / frontend port $port_fe / DB $db / Redis $redis
    branch: $branch

EOF
done

cat <<'EOF'
─── 主 worktree（merge train 协调） ───────────────────────────
    cd '"$main_repo"'
    （定期跑：git fetch --all → git merge feat/v1.1-* → push）

═════════════════════════════════════════════════════════════════
  完成。详见 docs/plans/2026-05-24-v1.1-multi-agent-plan.md
═════════════════════════════════════════════════════════════════
EOF
