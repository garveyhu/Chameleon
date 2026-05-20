# Chameleon CLI

入口由 `chameleon-app` 的 `[project.scripts]` 暴露。`uv sync` 后即可用：

```bash
uv run chameleon --help
```

或者激活 venv：

```bash
source .venv/bin/activate
chameleon --help
```

## 命令总览

```
Usage: chameleon [OPTIONS] COMMAND [ARGS]...

  Chameleon 命令行工具

Commands:
  init-admin   落第一个 admin scope api_key。明文仅一次回显，请立即保存。
  db           数据库迁移命令
```

## `chameleon init-admin`

在空库（或带 `--force`）落第一个具备 `admin` scope 的 API key。这是 bootstrap 流程，**之后所有 admin 操作走 HTTP**。

```bash
uv run chameleon init-admin --name <name> [--app-id <slug>] [--force]
```

### 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--name` | `admin` | 管理员名称（落入 `api_keys.name`） |
| `--app-id` | `admin-cli` | app_id slug（落入 `api_keys.app_id`） |
| `--force` | false | 即使已有 admin key 也强制新建 |

### 示例

**首次部署**：

```bash
uv run chameleon init-admin --name "links"
```

输出：

```
✓ Admin API key created
  app_id : admin-cli
  name   : links
  scopes : ['admin']

  KEY (仅一次回显，请立即保存)：
  chm_6d88WBWJy7kOV9myGYNpBp92tJtiydjA8codS6I7

  用法： curl -H 'Authorization: Bearer <KEY>' http://localhost:8000/v1/...
```

**幂等保护**：再次执行（无 `--force`）会被拒绝：

```bash
uv run chameleon init-admin
# ✗ 已存在 admin key (app_id=admin-cli)。如确需新建追加 --force
```

**追发第二个 admin**（团队多人时）：

```bash
uv run chameleon init-admin --name "alice" --app-id "alice-admin" --force
```

> ⚠️ 用 `--force` 不会撤老 key。如要撤销，请用 HTTP `POST /v1/admin/api-keys/{id}/revoke`。

## `chameleon db ...`

包装 alembic：

```bash
uv run chameleon db upgrade [revision]    # 默认 head
uv run chameleon db downgrade <revision>  # 回滚到指定 revision
```

实际执行的是 `alembic upgrade` / `alembic downgrade` 命令。
环境变量 `DATABASE_URL` 由 `migrations/env.py` 自动从 `config/.env` 读取。

### 示例

```bash
# 应用全部迁移
uv run chameleon db upgrade

# 回滚到 0001
uv run chameleon db downgrade 0001
```

## HTTP 管理（用 admin key）

CLI 仅做 bootstrap；其它管理操作走 HTTP：

```bash
ADMIN_KEY="chm_xxx..."

# 发普通 app key
curl -X POST http://localhost:8000/v1/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"my-app","name":"My App","scopes":[]}'

# 列出 keys（不含明文）
curl -H "Authorization: Bearer $ADMIN_KEY" \
  http://localhost:8000/v1/admin/api-keys

# 撤销
curl -X POST http://localhost:8000/v1/admin/api-keys/{id}/revoke \
  -H "Authorization: Bearer $ADMIN_KEY"

# 调用审计
curl -H "Authorization: Bearer $ADMIN_KEY" \
  "http://localhost:8000/v1/admin/call-logs?app_id=my-app&success=false"

# Provider 健康状态
curl -H "Authorization: Bearer $ADMIN_KEY" \
  http://localhost:8000/v1/admin/providers/status
```

## 未来扩展点（v0.2+）

CLI 设计为可扩展。如需要：

- `chameleon agents list` —— 显示当前注册的 agent
- `chameleon agents reload` —— 不重启 reload registry（需架构支持）
- `chameleon kb ingest --kb=x --file=y.md` —— 命令行 ingest
- `chameleon key revoke <id>` —— CLI 包装 HTTP

v1 不提供——HTTP 接口已覆盖。
