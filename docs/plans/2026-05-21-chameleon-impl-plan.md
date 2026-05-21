# Chameleon Redesign 实施计划

> **配套设计文档**：[2026-05-21-chameleon-redesign.md](./2026-05-21-chameleon-redesign.md)
> **状态**：Draft（待 review）
> **日期**：2026-05-21
>
> 本文档把 `redesign.md` 里描述的全部能力按依赖关系拆成 10 个 Phase。
> Phase 仅是执行顺序，不是发版边界——所有 Phase 完成一次性发版。

---

## 总览

```
P1 基础设施扩展
   │
   ├─→ P2 数据建模 ────────┐
   │                       │
   │                       ├─→ P3 鉴权与权限核心 ────┐
   │                       │                         │
   │                       └─→ P4 JSON↔DB seed       │
   │                            │                    │
   │                            └─→ P5 业务核心改造  │
   │                                 │               │
   │                                 ├──────────────┤
   │                                 │               ↓
   │                                 ├──→ P6 管理 API 实现
   │                                 │      │
   │                                 │      ↓
   │                                 └──→ P7 嵌入式后端
   │                                        │
   │                                        ↓
   └──────────────────────────────→ P8 前端核心页面 ──┐
                                                       │
                                                       ↓
                                                   P9 前端嵌入 widget
                                                       │
                                                       ↓
                                                   P10 收尾
```

**关键并行点**：
- P8（前端）依赖 P3（拿到 JWT API）即可启动，与 P5/P6 后端并行
- P10 收尾任务里的 i18n / docs 可在 P3+ 起就持续推进

---

## P1：基础设施扩展

**目标**：把 Redis / AES / argon2id / JWT 工具加入 `chameleon-core`，所有后续 Phase 都依赖。

**依赖**：— （直接开干）

### 任务清单

#### Task 1.1 - Redis 客户端集成

- [ ] `chameleon-core/.../infra/redis.py` 新建：暴露 `get_redis()` 单例 + lifespan 注册
- [ ] `chameleon-core/pyproject.toml` 加 `redis>=5.0`
- [ ] `backend/config/component.json` schema 加 `redis` 段（host / port / password / db）
- [ ] `chameleon.core.config.inventory.redis_config()` 函数
- [ ] `chameleon-app/.../main.py` lifespan 增加 Redis ping
- [ ] 单测：`test_redis_connection.py`

**验收**：起服务能 `redis-cli ping` 通；ping 失败启动 fail-fast。

#### Task 1.2 - AES-256-GCM 加密工具

- [ ] `chameleon-core/.../utils/crypto.py` 扩展：加 `encrypt_aes_gcm()` + `decrypt_aes_gcm()`
- [ ] Master key 从 env `CHAMELEON_MASTER_KEY`（base64 32 字节）读取
- [ ] dev 环境给默认 demo key + warn 日志
- [ ] prod 环境 master key 为空 → 启动 fail-fast
- [ ] 单测：`test_crypto.py` 覆盖加密 / 解密 / key 验证 / nonce 唯一

**验收**：加密文本 + 同 key 解密能还原；不同 key 解密报错。

#### Task 1.3 - argon2id 密码哈希

- [ ] `chameleon-core/.../utils/passwords.py` 新建
- [ ] `hash_password(plain) -> str` + `verify_password(plain, hashed) -> bool`
- [ ] 参数：time_cost=2, memory_cost=64MB, parallelism=1
- [ ] `chameleon-core/pyproject.toml` 加 `argon2-cffi>=23`
- [ ] 单测：`test_passwords.py`

**验收**：相同密码 hash 两次得到不同结果（盐随机）；verify 都能通过。

#### Task 1.4 - JWT 工具

- [ ] `chameleon-core/.../infra/jwt.py` 新建
- [ ] `encode_access_token(user_id, roles, **claims) -> str`（TTL 15min）
- [ ] `encode_refresh_token(user_id, jti) -> str`（TTL 7d）
- [ ] `decode_token(token) -> dict`（含黑名单检查）
- [ ] `revoke_token(jti, ttl_seconds)`（Redis SET）
- [ ] `is_revoked(jti) -> bool`
- [ ] JWT secret 从 env `CHAMELEON_JWT_SECRET` 读
- [ ] `chameleon-core/pyproject.toml` 加 `PyJWT[crypto]>=2.8`
- [ ] 单测：`test_jwt.py` 覆盖正常解码 / 过期 / 黑名单

**验收**：颁发 → 解码 → revoke → 解码失败完整链路通。

#### Task 1.5 - 雪花 ID 工具确认

- [ ] 复核 `chameleon-core/.../utils/snowflake.py` 已就绪
- [ ] 单测：`test_snowflake.py` 加并发场景测试

**验收**：高并发下 ID 唯一。

#### Task 1.6 - 配置加密落地到 component.json

- [ ] `config/example/component.example.json` 加 Redis 段示例
- [ ] `config/example/.env.example` 加 `CHAMELEON_MASTER_KEY`、`CHAMELEON_JWT_SECRET`、`REDIS_PASSWORD` 占位
- [ ] `docs/getting-started.md` 配置章节更新

**P1 完成标志**：

```bash
uv run pytest chameleon-core/tests/ -q  # 全过
```

---

## P2：数据建模

**目标**：14 张表的 ORM + Alembic 迁移落地。

**依赖**：P1（雪花 ID）

### 任务清单

#### Task 2.1 - ORM 模型（按域分文件）

`chameleon-core/.../models/` 下新建：

- [ ] `user.py`：User / Role / Permission / UserRole / RolePermission
- [ ] `app.py`：App / AppAgent
- [ ] `api_key.py`：ApiKey（重构）
- [ ] `provider.py`：Provider
- [ ] `model.py`：Model
- [ ] `agent.py`：Agent
- [ ] `kb.py`：KnowledgeBase / KbChunk
- [ ] `conversation.py`：Conversation / Message
- [ ] `call_log.py`：CallLog
- [ ] `embed_config.py`：EmbedConfig
- [ ] `audit_log.py`：AuditLog
- [ ] `setting.py`：Setting

**规约**：
- 所有模型继承 `BaseModel`（含 `id` 雪花 + `created_at` + `updated_at` + `deleted_at`）
- 字段类型用 SQLAlchemy 2.0 `Mapped[]` 风格
- 关系定义都用 `Mapped[List[Xxx]]` 显式声明

#### Task 2.2 - Alembic 迁移生成

- [ ] `backend/migrations/versions/2026-05-21-001-init-rbac.sql`（formatted SQL）
  - users + roles + permissions + user_roles + role_permissions
- [ ] `backend/migrations/versions/2026-05-21-002-apps-keys-refactor.sql`
  - apps + api_keys（含旧表 → 新表数据迁移）
  - app_agents
- [ ] `backend/migrations/versions/2026-05-21-003-models-providers.sql`
  - providers + models
- [ ] `backend/migrations/versions/2026-05-21-004-agents-table.sql`
- [ ] `backend/migrations/versions/2026-05-21-005-call-logs-extend.sql`
  - 字段扩展（加 api_key_id / duration_ms / prompt_tokens / completion_tokens）
- [ ] `backend/migrations/versions/2026-05-21-006-embed-configs.sql`
- [ ] `backend/migrations/versions/2026-05-21-007-audit-settings.sql`
  - audit_logs + settings
- [ ] `backend/migrations/versions/2026-05-21-008-indexes.sql`
  - 所有 §3.2 列出的索引

**规约**：
- 一律 formatted SQL（含 `--rollback`），不用结构化标签
- 数据迁移与 DDL 拆独立 changeSet（参考 java-codebase.md）

#### Task 2.3 - ORM 单测

- [ ] 每个 model 文件对应 `tests/test_<model>.py`
- [ ] 覆盖：创建 / 查询 / 关系加载 / 软删过滤 / 唯一约束

**P2 完成标志**：

```bash
uv run alembic upgrade head           # 全 8 个迁移成功
uv run pytest chameleon-core/tests/ -q  # 全过
```

---

## P3：鉴权与权限核心

**目标**：JWT 双 token + RBAC 中间件可用。

**依赖**：P1 + P2

### 任务清单

#### Task 3.1 - 鉴权服务模块

`chameleon-system/.../auth/` 新建：

- [ ] `service.py`：login / refresh / logout / change_password
- [ ] `schemas.py`：LoginRequest / TokenPair / RefreshRequest 等 DTO
- [ ] `api.py`：`/v1/auth/*` 路由
- [ ] `dependencies.py`：FastAPI dependency
  - `get_current_user()`：解 access_token → User
  - `require_role(*roles)`：角色守卫
  - `require_permission(*perms)`：权限守卫

#### Task 3.2 - JWT cookie 处理

- [ ] login 接口 set HTTP-only cookie：`refresh_token`（path=/v1/auth, secure, samesite=lax）
- [ ] refresh 接口从 cookie 读 refresh_token，验签后吊销旧 jti + 颁新对
- [ ] logout 接口 revoke access jti + 清 cookie

#### Task 3.3 - RBAC dependency

- [ ] `require_permission("agents:write")` 装饰 router
- [ ] 检查顺序：access_token 有效 → 黑名单未中 → user.status active → 用户角色聚合 permission set → 含目标 perm

#### Task 3.4 - 错误码体系扩展

`chameleon-core/.../api/exceptions.py` 加：

- [ ] `ResultCode.JwtExpired = 4101`
- [ ] `ResultCode.JwtInvalid = 4102`
- [ ] `ResultCode.PermissionDenied = 4103`
- [ ] `ResultCode.RefreshTokenInvalid = 4104`
- [ ] `ResultCode.LoginRateLimit = 4105`
- [ ] `ResultCode.AccountDisabled = 4106`
- [ ] 对应异常类 + handler

#### Task 3.5 - 登录速率限制

- [ ] Redis-backed 计数器：key `chameleon:login_attempts:{ip|username}`
- [ ] 5 次失败 → 锁定 15 分钟 → 返 `LoginRateLimit`
- [ ] 成功登录清计数

#### Task 3.6 - 测试

- [ ] `tests/test_auth_login.py`
- [ ] `tests/test_auth_refresh.py`
- [ ] `tests/test_auth_logout.py`
- [ ] `tests/test_rbac_dependencies.py`
- [ ] `tests/test_rate_limit.py`

**P3 完成标志**：

```bash
# E2E 走通
curl -X POST .../v1/auth/login -d '{"username":"x","password":"y"}'
# → 200 + access_token + cookie

curl -H "Authorization: Bearer <token>" .../v1/auth/me
# → 200 + 用户信息

curl -H "Authorization: Bearer <token>" .../v1/admin/users
# → 200 / 403 (按角色)
```

---

## P4：JSON ↔ DB seed 与同步

**目标**：首次启动自动 seed，常态运行以 DB 为准；导入 / 导出 zip 备份能力。

**依赖**：P2（表已建）+ P3（admin 用户能 seed）

### 任务清单

#### Task 4.1 - seed 流程主控

`chameleon-system/.../settings/seed.py`：

- [ ] `run_seed_if_empty()` 入口（lifespan 调用）
- [ ] 判空逻辑：`users` 表无 row → seed
- [ ] seed 步骤按顺序：
  1. seed default permissions（从 hardcoded list 写入）
  2. seed default roles（admin / developer / viewer）
  3. seed default admin user（强随机密码 + 首次登录强改密 flag）
  4. seed providers + models from `model.json`
  5. seed external agents from `agents.yaml` + 扫本地 agents 入表
  6. seed default app + admin's api_key（如有旧 admin key 迁移）
  7. seed settings defaults

#### Task 4.2 - 启动期 admin credentials 写文件

- [ ] seed 产生的随机密码 → 写 `backend/logs/initial-admin-credentials.txt`（chmod 600）
- [ ] 同时打到 startup log 一次（红色 highlight）
- [ ] log 里只显示用户名，密码靠文件

#### Task 4.3 - 配置加密落地

- [ ] `providers.api_key_encrypted` 字段：seed 时用 master_key 加密 model.json 里的 plaintext
- [ ] 读取时（任何 LLMFactory call）从 DB 取 + 解密
- [ ] 加 cache（30s TTL 减少加解密开销）

#### Task 4.4 - 导出 zip 备份

`POST /v1/admin/settings/export-json`：

- [ ] 生成 zip 含：
  - `model.json`（从 providers + models 表反推）
  - `agents.yaml`（从 agents 表 external 子集）
  - `chameleon.json`（从 settings 表）
  - `apps.json`（apps + api_keys，key_hash 不可还原）
  - `users.json`（users + user_roles + roles，含 password_hash）
  - `embed_configs.json`
  - `README.md`：说明文件用途与还原方法
- [ ] 文件名：`chameleon-backup-YYYY-MM-DD-HHmmss.zip`
- [ ] 仅 admin 角色可下载

#### Task 4.5 - 导入 zip 备份

`POST /v1/admin/settings/import-json`（multipart upload）：

- [ ] 仅 admin
- [ ] 上传 zip → 解压 → 逐表 UPSERT
- [ ] 危险操作 → 要求二次确认参数 `confirm=true`
- [ ] 导入完成生成 audit_log

#### Task 4.6 - 单测

- [ ] `test_seed_default_admin.py`
- [ ] `test_seed_idempotent.py`：第二次 seed 不重复插入
- [ ] `test_provider_encrypt_roundtrip.py`
- [ ] `test_export_import_zip.py`

**P4 完成标志**：

```bash
# 启动空 DB 服务
uv run uvicorn chameleon.app.main:app
# → 看到 "✓ seeded admin / username=admin / password=xxx → see logs/initial-admin-credentials.txt"

# 登录改密 → 改 model → 导出
curl ... /v1/admin/settings/export-json -o backup.zip
unzip -l backup.zip  # 验证 7 个文件

# 干掉 DB 重建 → 导入还原
docker exec postgres dropdb -U collector chameleon
uv run alembic upgrade head
curl -X POST ... /v1/admin/settings/import-json -F file=@backup.zip -F confirm=true
# → 数据全部还原（除随机密码）
```

---

## P5：业务核心改造

**目标**：LLMFactory / Provider registry / Agent registry 全部从 DB 读，不再依赖 JSON。

**依赖**：P4（seed 完成后 DB 有数据）

### 任务清单

#### Task 5.1 - LLMFactory DB 化

- [ ] `chameleon-core/.../components/llms/factory.py` 改：从 DB 取 provider + model 配置
- [ ] 加缓存层：Redis SET `chameleon:cache:llm:{provider_id}:{model_code}` TTL 30s
- [ ] 写操作（admin 改 model / provider）→ `DEL` 对应 cache
- [ ] `provider.api_key_encrypted` → 解密注入到 LLM client
- [ ] 单测：`test_llm_factory_db_driven.py`

#### Task 5.2 - Provider registry DB 化

- [ ] `chameleon-providers/base/.../registry.py` 改：扫 namespace 同时合并 DB providers 表
- [ ] 外部 provider 实例配置（base_url / api_key）从 DB 读
- [ ] 本地 provider（local）固定，无 DB 配置
- [ ] 启动 log 区分：built-in providers / db-configured providers

#### Task 5.3 - Agent registry DB 化

- [ ] `chameleon-providers/base/.../registry.py` 改 `_build_local_agents()`：扫 namespace + 查 DB `agents` 表过滤启用态
- [ ] 改 `_build_yaml_agents()` → `_build_external_agents_from_db()`：从 DB `agents` 表 source != 'local' 子集读
- [ ] 本地 agent 在 DB 里没有 → 自动入表（enabled=true）
- [ ] 本地 agent 在 DB 里 enabled=false → 跳过加载
- [ ] 单测：`test_agent_registry_db_driven.py`

#### Task 5.4 - 配置失效机制

- [ ] `chameleon-system/.../settings/cache.py` 新建：cache invalidation helpers
- [ ] CRUD 端点写 DB 完成后调用 `invalidate_*` 删 Redis key
- [ ] 影响 registry 的字段改动（agent.enabled / provider.api_key 等）→ 调用 `reload_registry()` 内存重建

**P5 完成标志**：

```bash
# 前端关掉某个 agent → 业务 API 立即返 404 not found
curl ... /v1/admin/agents/123/disable
curl ... /v1/agents/my-faq/invoke  # → 404

# 前端改 LLM api_key → 下次调用立即生效
curl ... /v1/admin/providers/5/update -d '{"api_key": "sk-new"}'
curl ... /v1/agents/qwen-chat/invoke  # → 用新 key 调通
```

---

## P6：管理 API 实现

**目标**：完整 `/v1/admin/*` 所有端点。

**依赖**：P3 + P5

### 任务清单

按 chameleon-system 子模块拆：

#### Task 6.1 - users / roles / permissions API

`chameleon-system/.../users/` + `roles/` + `permissions/`：

- [ ] `GET/POST/POST update/POST delete /v1/admin/users`
- [ ] `POST /v1/admin/users/{id}/roles/grant|revoke`
- [ ] `GET/POST/POST update/POST delete /v1/admin/roles`
- [ ] `POST /v1/admin/roles/{id}/permissions/sync`
- [ ] `GET /v1/admin/permissions`（只读）

#### Task 6.2 - apps / api_keys API

`chameleon-system/.../apps/`：

- [ ] `GET/POST/POST update/POST delete /v1/admin/apps`
- [ ] `GET/POST /v1/admin/apps/{id}/api-keys`
- [ ] `POST /v1/admin/api-keys/{id}/revoke`
- [ ] `POST /v1/admin/apps/{id}/agents/grant|revoke`（授权 agent）

#### Task 6.3 - providers / models API

`chameleon-system/.../providers/` + `models/`：

- [ ] `GET/POST/POST update/POST delete /v1/admin/providers`
- [ ] `POST /v1/admin/providers/{id}/test`（连通性测试）
- [ ] `GET/POST/POST update/POST delete /v1/admin/models`

#### Task 6.4 - agents 管理 API

`chameleon-system/.../agents/`：

- [ ] `GET /v1/admin/agents`（本地 + 外部全列出，本地 read-only）
- [ ] `POST /v1/admin/agents`（仅 source!=local）
- [ ] `POST /v1/admin/agents/{id}/update`
- [ ] `POST /v1/admin/agents/{id}/delete`（local 拒绝）
- [ ] `POST /v1/admin/agents/{id}/enable`
- [ ] `POST /v1/admin/agents/{id}/disable`
- [ ] `POST /v1/admin/agents/{id}/test`（一次 invoke 看结果）

#### Task 6.5 - kbs / chunks 管理 API

`chameleon-system/.../kbs/`：

- [ ] `GET /v1/admin/kbs`（含统计）
- [ ] `POST /v1/admin/kbs/{id}/update`
- [ ] `POST /v1/admin/kbs/{id}/delete`
- [ ] `GET /v1/admin/kbs/{id}/chunks`（分页 + 全文搜索）

#### Task 6.6 - call_logs 查询

`chameleon-system/.../call_logs/`：

- [ ] `GET /v1/admin/call-logs`（分页 + 过滤 app/agent/status/时间）
- [ ] `GET /v1/admin/call-logs/{id}`（含完整 messages snapshot）

#### Task 6.7 - dashboard API

`chameleon-system/.../dashboard/`：

- [ ] `GET /v1/admin/dashboard/overview`：今日 / 本周调用量 / 错误率 / token / 活跃 app 数
- [ ] `GET /v1/admin/dashboard/timeseries?metric=qps&granularity=hour&from=&to=`
- [ ] `GET /v1/admin/dashboard/top-agents?limit=10`
- [ ] `GET /v1/admin/dashboard/top-apps?limit=10`

#### Task 6.8 - settings + audit_logs

`chameleon-system/.../settings/`：

- [ ] `GET /v1/admin/settings`
- [ ] `POST /v1/admin/settings/update`
- [ ] `POST /v1/admin/settings/export-json`（Task 4.4）
- [ ] `POST /v1/admin/settings/import-json`（Task 4.5）

`chameleon-system/.../audit_logs/`：

- [ ] `GET /v1/admin/audit-logs`（分页）
- [ ] audit_log 写入中间件：所有 admin 写操作自动写一条

#### Task 6.9 - 单元测试

每个子模块对应 `tests/test_<module>_api.py`，覆盖：
- happy path
- 权限不足
- 输入校验失败
- 资源不存在

**P6 完成标志**：

```bash
# 全 API 走通
pytest chameleon-system/tests/ -q
```

OpenAPI 文档 `/docs` 看到完整管理 API 列表。

---

## P7：嵌入式后端

**目标**：embed_configs CRUD + `/v1/embed/*` 业务接口。

**依赖**：P5 + P6

### 任务清单

#### Task 7.1 - embed_configs 管理 API

`chameleon-system/.../embed_configs/`：

- [ ] `GET/POST/POST update/POST delete /v1/admin/embed-configs`
- [ ] 创建时生成短码 `emb_<8 base62>` （唯一）
- [ ] 字段：name / agent_id / app_id / allowed_origins / ui_config / behavior

#### Task 7.2 - 嵌入式调用 API

`chameleon-api/.../embed/`（新模块）：

- [ ] `GET /v1/embed/{embed_key}/config`：返回 ui_config + behavior，校验 origin 在白名单
- [ ] `POST /v1/embed/{embed_key}/session`：颁发 embed_session_token（Redis SET，TTL 1h）
- [ ] `POST /v1/embed/{embed_key}/invoke`：用 embed_session_token 鉴权，调对应 agent

#### Task 7.3 - CORS + 限流

- [ ] FastAPI CORSMiddleware 为 `/v1/embed/*` 单独配置
- [ ] 动态 origin 校验：根据 embed_configs.allowed_origins 拒绝
- [ ] embed_session_token 限速：5 msg/min/token（Redis INCR）

#### Task 7.4 - 单测

- [ ] `test_embed_config_crud.py`
- [ ] `test_embed_origin_whitelist.py`
- [ ] `test_embed_session_lifecycle.py`
- [ ] `test_embed_rate_limit.py`

**P7 完成标志**：

```bash
# 创建 embed config
curl ... /v1/admin/embed-configs -d '{"agent_id":1,"allowed_origins":["https://example.com"]}'

# 模拟业务方网页（带 Origin header）调
curl -H "Origin: https://example.com" .../v1/embed/emb_xxx/config  # 200
curl -H "Origin: https://evil.com" .../v1/embed/emb_xxx/config    # 403
```

---

## P8：前端脚手架 + 核心页面

**目标**：完整管理面板前端。

**依赖**：P3 完成即可启动（拿到 auth API）；可与 P5-P7 并行

### 任务清单

#### Task 8.1 - 脚手架

`frontend/` 下：

- [ ] `npm create vite@latest . -- --template react-ts`
- [ ] 装：tailwind / shadcn-cli / react-router-dom / @tanstack/react-query / zustand / axios / react-hook-form / zod / recharts / i18next / react-i18next
- [ ] `tailwind.config.ts` + `postcss.config.js`
- [ ] shadcn 初始化：`npx shadcn@latest init`
- [ ] 目录结构按 `~/.claude/rules/react-codebase.md` 规范

```
frontend/src/
├── pages/             # 路由级
│   ├── auth/login/
│   ├── dashboard/
│   ├── users/
│   ├── roles/
│   ├── apps/
│   ├── providers/
│   ├── agents/
│   ├── kbs/
│   ├── call-logs/
│   ├── embed-configs/
│   ├── settings/
│   └── audit-logs/
├── components/        # 通用组件
├── hooks/             # 通用 hooks
├── services/          # API 调用（按业务模块切）
│   ├── auth.ts
│   ├── users.ts
│   ├── apps.ts
│   └── ...
├── stores/            # zustand
│   ├── authStore.ts
│   └── themeStore.ts
├── utils/
├── types/
├── locales/           # i18n
│   ├── zh-CN/
│   └── en-US/
└── config/
    ├── routes.tsx
    └── theme.ts
```

#### Task 8.2 - axios 封装

- [ ] `services/_http.ts`：
  - 注入 access_token header
  - 拦截 401 → 自动 refresh → 重试
  - 解包 `Result[T]` 外壳
  - 错误统一 toast

#### Task 8.3 - 路由与权限守卫

- [ ] `config/routes.tsx`：路由表
- [ ] `<RequireAuth>` 组件：未登录跳 login
- [ ] `<RequirePermission perm="agents:write">` 组件：无权限跳 403 页
- [ ] 路由对应权限点配置

#### Task 8.4 - 登录页 + 首次改密页

- [ ] `pages/auth/login/LoginPage.tsx`
- [ ] `pages/auth/first-password/FirstPasswordPage.tsx`
- [ ] login 成功 → 检查 user.must_change_password → 跳改密 → 跳 dashboard

#### Task 8.5 - 主布局

- [ ] `components/Layout`：侧边栏 + topbar + 主区
- [ ] 侧边栏菜单按权限过滤
- [ ] 顶部：搜索 / 通知 / 用户菜单 / 切换语言

#### Task 8.6 - Dashboard 页

- [ ] 4 张统计卡片（今日调用 / 错误率 / token 消耗 / 活跃 app）
- [ ] 折线图：最近 24h QPS（recharts）
- [ ] top agents / top apps 列表

#### Task 8.7 - 12 大类页面 CRUD

每页 deliverable：列表（分页 + 过滤）+ 创建抽屉 + 编辑抽屉 + 删除确认 + 详情页（如需）。

- [ ] Users
- [ ] Roles + 权限分配（穿梭框 / tree）
- [ ] Apps + API Keys（apps 列表 → 点开看 keys 子列表 + 授权 agents）
- [ ] Providers（CRUD + 连通性测试按钮）
- [ ] Models（按 provider 分组）
- [ ] Agents（启用开关 + 测试调用抽屉，含 stream 展示）
- [ ] Knowledge Bases（CRUD + 文档上传进度 + 切块查看）
- [ ] Call Logs（分页 + 过滤 + 详情）
- [ ] Embed Configs（CRUD + 嵌入代码生成器，复制 HTML snippet）
- [ ] Settings（系统配置 + 导入 / 导出 JSON 按钮）
- [ ] Audit Logs

#### Task 8.8 - 国际化集成

- [ ] i18next 初始化（默认 zh-CN，浏览器探测）
- [ ] 翻译文件按 namespace 拆（auth / agents / models / ...）
- [ ] 顶部语言切换按钮

#### Task 8.9 - 测试

- [ ] `frontend/tests/unit/`：关键 hook / utils
- [ ] `frontend/tests/e2e/`：Playwright 覆盖登录 + 主流 CRUD + dashboard 渲染

**P8 完成标志**：

```bash
cd frontend && npm run dev
# → http://localhost:5173 看到登录页
# 登录 admin → 看到 dashboard
# 走完所有 12 类页面 CRUD 无 bug
```

---

## P9：前端嵌入式 widget

**目标**：`frontend/embed/` 独立子工程，构建出 widget UMD + iframe。

**依赖**：P7（embed 后端 API）+ P8（admin 前端能创建 embed_config）

### 任务清单

#### Task 9.1 - embed 子工程脚手架

`frontend/embed/` 独立 Vite 项目：

- [ ] `frontend/embed/package.json`
- [ ] `frontend/embed/vite.config.ts`：build 模式 UMD + 单 chunk
- [ ] 入口：`src/widget.ts`（暴露挂载到 window）+ `src/iframe.tsx`（iframe 模式独立页）

#### Task 9.2 - Widget UMD

- [ ] `widget.ts`：自动检测 `<script data-embed-key="xxx">` 元素，读 key
- [ ] GET `/v1/embed/{key}/config` 拉 UI config
- [ ] 渲染右下角浮动气泡
- [ ] 点开 → 展开对话面板（zero-config 主题）
- [ ] POST session → 拿 embed_session_token → invoke 调用
- [ ] bundle 体积 ≤ 200KB（gzip）

#### Task 9.3 - Iframe 模式

- [ ] `src/iframe.tsx`：独立全屏对话页
- [ ] 路由 `/embed/{key}` 直接嵌入：`<iframe src="...">`
- [ ] 主题色 / 欢迎语等从 config 拉

#### Task 9.4 - admin 前端集成

- [ ] Embed Configs 页加"嵌入代码生成器"
- [ ] 选择 widget 模式 → 复制 `<script ...>` snippet
- [ ] 选择 iframe 模式 → 复制 `<iframe ...>` snippet

#### Task 9.5 - 测试

- [ ] `frontend/embed/tests/`：单测
- [ ] Playwright E2E：起一个真业务方页面 → 嵌入 widget → 跑通对话

**P9 完成标志**：

```html
<!-- 写一个 demo.html -->
<script src="http://localhost:5173/widget.js" data-embed-key="emb_xxx" defer></script>
```

打开 demo.html → 右下角自动出气泡 → 点开能对话。

---

## P10：收尾——国际化 / 测试 / 文档 / Docker

**目标**：交付级整理，可对外发布。

**依赖**：前面全部完成

### 任务清单

#### Task 10.1 - 后端国际化完整化

- [ ] `chameleon-core/.../i18n/zh-CN/errors.json` + `en-US/errors.json`
- [ ] `Result.fail(code, message_id)` 改造支持 message_id 翻译
- [ ] 中间件解析 `Accept-Language`
- [ ] 单测覆盖中英文消息切换

#### Task 10.2 - 测试覆盖完善

- [ ] 后端单测覆盖率 ≥ 80%（pytest-cov）
- [ ] 集成测试用 testcontainers 起真 PG + Redis
- [ ] 前端 Vitest 覆盖率
- [ ] Playwright 全 E2E 套件

#### Task 10.3 - CI/CD

- [ ] `.github/workflows/backend-ci.yml`
- [ ] `.github/workflows/frontend-ci.yml`
- [ ] `.github/workflows/e2e.yml`
- [ ] `.github/workflows/release.yml`（打 tag → 构建 docker → push ghcr.io）

#### Task 10.4 - Docker 化

- [ ] `backend/Dockerfile` multi-stage（uv build → slim runtime）
- [ ] `frontend/Dockerfile` multi-stage（node build → nginx）
- [ ] `docker-compose.yml`（PG + Redis + backend + frontend）
- [ ] `docker-compose.cn.yml` overlay（阿里云镜像源）
- [ ] `Makefile` 或 `scripts/dev.sh` 一键起

#### Task 10.5 - 文档双语

`docs/` 顶层维持 zh-CN 主要文档，加 `docs/en/` 子目录翻译核心：

- [ ] README.md ↔ README.en.md
- [ ] docs/getting-started.md ↔ docs/en/getting-started.md
- [ ] docs/admin-guide.md（新）↔ docs/en/admin-guide.md
- [ ] docs/api-reference.md（新）↔ docs/en/api-reference.md
- [ ] docs/architecture.md（基于 redesign.md 精简）↔ docs/en/architecture.md
- [ ] docs/deployment.md（基于 P10.4）↔ docs/en/deployment.md

#### Task 10.6 - ADR 文档

`docs/adr/`：

- [ ] 0001-jwt-double-token.md
- [ ] 0002-rbac-classic-three-tables.md
- [ ] 0003-json-seed-db-runtime.md
- [ ] 0004-shadcn-over-antd.md
- [ ] 0005-redis-for-jwt-blacklist.md
- [ ] 0006-aes-gcm-provider-keys.md
- [ ] 0007-no-multitenancy-yet.md
- [ ] 0008-no-celery-yet.md
- [ ] 0009-embed-widget-design.md
- [ ] 0010-frontend-vite-spa.md

#### Task 10.7 - lint + 类型检查全过

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run mypy chameleon-*/` 加入 CI
- [ ] frontend `npm run lint && npm run type-check`

#### Task 10.8 - 性能 smoke check

- [ ] 简单 locust 脚本（不是 SLO，只是 smoke）
  - 登录 100 QPS 不爆
  - 本地 agent invoke 50 QPS 不爆
  - dashboard query 10 QPS 不爆

#### Task 10.9 - 发布前 checklist

- [ ] 全测试通过
- [ ] CI 全绿
- [ ] docker-compose up -d 一键起在干净机器跑通
- [ ] README 双语
- [ ] CHANGELOG.md
- [ ] tag v1.0.0
- [ ] 验收报告 `docs/plans/2026-05-21-chameleon-acceptance-report.md`

**P10 完成标志**：在干净的机器上：

```bash
git clone <repo>
cd Chameleon
docker compose up -d
# → 等待 1 分钟
open http://localhost:3000
# → 看到登录页 → 用 docker logs backend | grep admin 拿到初始密码 → 登录 → 全功能正常
```

---

## 全 Phase 任务统计

| Phase | 任务数 | 测试数 |
|---|---|---|
| P1 | 6 | 5 |
| P2 | 3 | 12 |
| P3 | 6 | 5 |
| P4 | 6 | 4 |
| P5 | 4 | 2 |
| P6 | 9 | 8 |
| P7 | 4 | 4 |
| P8 | 9 | 2 套 |
| P9 | 5 | 1 套 |
| P10 | 9 | — |
| **总计** | **61 个主任务** | **大量** |

---

## 风险与回滚

### 高风险点

| 风险 | 缓解 |
|---|---|
| JSON → DB 迁移期间数据丢失 | P4 用 git tag 标记迁移前快照；导出 zip 备份 |
| JWT secret 泄漏 | 限定文件权限 + 不入 git；旋转机制（P10.7 后视情况） |
| Master key 丢失 → provider api_key 解不开 | 启动失败时显示明确错误信息引导从 backup zip 还原 |
| RBAC 权限漏洞（越权） | 测试覆盖必须含越权场景；security review |
| 前端 axios 拦截器 refresh 死循环 | 状态机限制 refresh 重试 1 次 |
| embed widget XSS | 严格 markdown safe 渲染；CSP nonce |

### 回滚机制

- 每个 Phase 完成立 git tag `phase-NN-done`
- 任一 Phase 失败 → `git reset --hard phase-NN-1-done`
- DB 迁移每条 changeSet 必带 `--rollback`，可单步回滚

---

## 进度跟踪建议

- Phase 完成 → commit message：`feat(<scope>): P<N> 完成 — <主要 deliverable>`
- 每个 Phase 完成生成简短 phase report：`docs/plans/phase-N-report.md`（成果 + 偏离记录 + 给下个 Phase 的注意点）
- 全部完成发布 → 写 `docs/plans/2026-05-21-chameleon-acceptance-report.md`（参考 v0.1 acceptance report 风格）

---

## 下一步

1. **你 review** 设计文档 + 本实施计划 → 标 OK / 需调整
2. 我开始按 P1 → P2 → ... 顺序实施
3. 每 Phase 完成做一次 review point（你判断要不要继续 / 调整方向）
