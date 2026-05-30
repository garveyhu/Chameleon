# Chameleon 运维手册

## 部署模型

Chameleon 是单进程 FastAPI app（薄启动器 `chameleon-app` 装配 10 个 uv-workspace 包：core / data / integrations / engine / providers / agents / agentkit / api / system / app）。生产部署：

- 1×（或更多）uvicorn worker 跑 `chameleon.app.main:app`
- **PostgreSQL 16 + pgvector**：业务库 + trace（call_logs）+ 向量检索都在这里
- **Redis**：启动 `_lifespan` 内 ping，**不通即 fail-fast**（JWT 黑名单 / 限流 / 配置缓存全靠它）
- **MinIO（对象存储）**：知识库文档原文 / 会话文件落对象存储（不落本地盘）；不可用时 KB 上传会失败（warn-only，不 fail-fast）
- 异步 ingest worker 与 web worker 同进程（FastAPI lifespan 内 `asyncio.create_task` 派发）；eval 调度、human-input 超时清扫等 cron 也在 lifespan 内拉起

## 配置与环境变量

配置主体在 JSON 配置文件里（`backend/config/`），`.env` **只放部署级 override**：

| 配置文件 | 内容 |
|---|---|
| `config/component.json` | DB / Redis / MinIO 连接信息 |
| `config/chameleon.json` | 业务参数（`log_level` / `session` / `knowledge.embedding_dim` / `provider_timeout_ms` / `call_log.retention_days` 等） |
| `config/model.json` | LLM provider + key（`providers.*.key_env` 引用环境变量） |
| `config/agents.yaml` | 外部 agent（Dify / FastGPT）注册，`${env:XXX}` 占位符引用 key |

环境变量（`.env` 或容器注入，多数可选——只在 override / 容器化 / 生产加固时填）：

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `DATABASE_URL` | | 从 `component.json` 拼 | 设了就 override，如 `postgresql+asyncpg://user:pwd@host:port/chameleon` |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | | 从 `component.json` 拼 | 任一未设 → 走 `component.json` |
| `LOG_LEVEL` | | INFO | override `chameleon.json` 的 `log_level`；DEBUG / INFO / WARNING / ERROR |
| `CHAMELEON_ENV` | | — | 设 `production` 时缺 crypto key / JWT secret 会 **fail-fast** |
| `CHAMELEON_CRYPTO_KEY` | 生产✅ | dev demo | AES-256-GCM 主密钥（base64 32 字节），加密 `providers.api_key` 等敏感字段 |
| `CHAMELEON_JWT_SECRET` | 生产✅ | dev demo | 签 access / refresh token（base64 ≥ 32 字节） |
| `CHAMELEON_INSTANCE_ID` | | 0 | 多实例部署时区分（雪花 ID 用） |
| `CHAMELEON_ROOT` | | 相对推算 | Docker 中指向项目根（`config/` / `logs/` 据此推算） |
| `CHAMELEON_DATA` | | `$ROOT/resources` | 数据目录 |
| `CHAMELEON_LOG_DIR` | | `$ROOT/logs` | 日志目录 |
| LLM `*_API_KEY` | 按需 | — | 与 `config/model.json` 里 `providers.*.key_env` 对应 |
| 外部 agent `*_KEY` | 按需 | — | 与 `config/agents.yaml` 里 `${env:XXX}` 对应 |

生成 crypto key / JWT secret：

```bash
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

详见 [config/example/.env.example](../backend/config/example/.env.example)。

## 起服务

### 开发模式

```bash
uv run uvicorn chameleon.app.main:app --reload --host 127.0.0.1 --port 7009
```

启动后 lifespan 会按序初始化（crypto / JWT → Redis ping → MinIO bucket 自检 → seed → LLM cache → registry），并打印已注册的 providers 和 agents：

```
Redis connected
─── Chameleon Registry ───
Loaded N providers: local, dify, fastgpt, graph
Loaded N agents:
  [local    ] qwen-chat                  (built-in)
  [dify     ] customer-faq               (from agents.yaml)
  [graph    ] my-workflow                (graph published as agent)
  ...
```

> provider 抽象在 `chameleon-providers`：`local`（进程内 BaseAgent）/ `dify` / `fastgpt` / `graph`（工作流即 agent）。

### 生产模式（裸 uvicorn）

```bash
uv run uvicorn chameleon.app.main:app \
  --host 0.0.0.0 --port 7009 \
  --workers 4 \
  --proxy-headers --forwarded-allow-ips='*'
```

### 反向代理（Nginx）SSE 配置

⚠️ Nginx 默认会缓冲响应——必须为流式 invoke 端点（`POST /v1/invoke`、OpenAI 兼容的 `/v1/chat/completions`、嵌入式 `/v1/embed/*`）关掉缓冲，否则流式不流。

Chameleon 已在 StreamingResponse 响应头加 `X-Accel-Buffering: no`，Nginx 1.5.6+ 会识别。也可显式配置：

```nginx
location /v1/ {
    proxy_pass http://chameleon-upstream;
    proxy_buffering off;
    proxy_cache off;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_read_timeout 600s;     # 长流式
}
```

## Alembic 数据库迁移

### 常用命令

```bash
# 应用全部迁移
uv run alembic upgrade head

# 回滚一步
uv run alembic downgrade -1

# 看当前 revision
uv run alembic current

# autogenerate（先改 ORM，再生成）
uv run alembic revision --autogenerate -m "add foo column"
```

`alembic.ini` 的 `sqlalchemy.url` 留空——`migrations/env.py` 走 `chameleon.core.config.inventory.database_url()`：优先 env `DATABASE_URL`（容器化 override），否则从 `config/component.json` 的 `database.*` 拼。

### 红线（严格遵守）

1. **已发布的 migration 脚本绝不再改**（checksum 跑挂）
2. 新增 migration 必带 `--rollback` / `downgrade()`
3. pgvector 维度若改（默认锁 1536，`chunks.embedding` 与 `config/chameleon.json` 的 `knowledge.embedding_dim` 对齐）→ **新 migration + 老数据 re-embed**，不能 in-place ALTER
4. 大表加列加索引前评估锁影响（HNSW 索引建索引慢 + 占内存）
5. 不在 migration 里调 ORM 类（migration 是 schema 的快照，ORM 是当前态——分离）

### migration 链

迁移脚本在 `backend/migrations/versions/`，是一条单向链（不是定版的两张表）：

```
0001_enable_pgvector       —— CREATE EXTENSION vector
0002_initial_tables        —— 初始业务表 + chunks HNSW(cosine, m=16, ef_construction=64)
…                          —— 历次 schema 演进（含 sessions 改造 / call_logs span 维度 /
                              KB collections / 删除已弃用概念表 等）
p26_d01_drop_graph_node_runs —— 当前 head
```

查当前链头与历史：

```bash
uv run alembic heads      # 当前 head revision
uv run alembic history    # 完整链
```

> ORM 模型在 `backend/chameleon-data/src/chameleon/data/models/`，是判断"现在到底有哪些表"的事实源。

## 备份与恢复

### 备份

```bash
# 只备 chameleon 库（不动 wave_obs 等共享实例的其它库）
docker exec postgres pg_dump -U collector -d chameleon -Fc \
  > backups/chameleon-$(date +%Y%m%d-%H%M%S).dump
```

**估算 chunks 表大小**：每个 chunk ≈ `(1536 * 4 bytes) + len(content) + meta`。
即 ≈ **6KB / chunk**（1536 维 float32）。
1 万 chunks ≈ 60MB；100 万 ≈ 6GB。

> 知识库文档原文 / 会话文件落 MinIO（对象存储），不在 PostgreSQL 里——容灾时对象存储要单独备份。

### 恢复

```bash
docker exec -i postgres pg_restore -U collector -d chameleon --clean --if-exists \
  < backups/chameleon-YYYYMMDD-HHMMSS.dump
```

### HNSW 索引重建（罕用）

如果 HNSW 索引坏掉（OOM、文件损坏）：

```sql
DROP INDEX ix_chunks_embedding_hnsw;
CREATE INDEX ix_chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

重建期间查询会走全表扫——服务不中断但慢。

## 日志

- 路径：`$CHAMELEON_LOG_DIR/chameleon.log`（默认 `logs/chameleon.log`）
- rotation：50 MB / 文件，保留 7 天，gzip 压缩历史
- 同时输出 stdout（开发友好）

uvicorn / sqlalchemy / httpx 的 stdlib logging 已被 loguru 接管，格式统一。

## 升级流程

```bash
# 1. 备份
docker exec postgres pg_dump -U collector -d chameleon -Fc > backups/before-upgrade.dump

# 2. 拉新代码（uv workspace：同步全部包）
git pull
uv sync --all-packages

# 3. 看新 migration
uv run alembic history
uv run alembic upgrade head

# 4. 重启
# kill 老的 uvicorn，启动新的
```

## 调用审计（call_logs）

`call_logs` 是**唯一 trace 真相源**——每次 invoke / LLM 调用落一行，graph 节点发 span 进同一棵 trace 树，根行 rollup（model / token / cost）。

admin API 走 JWT 登录 + RBAC（`require_permission`），不是静态 admin key。先登录拿 access token：

```bash
TOKEN=$(curl -s -X POST http://localhost:7009/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<password>"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
```

查 call_logs（需 `call_logs:read` 权限），支持 `agent_key` / `channel` / `model_code` / `session_id` / `end_user_id` / `since` / `until` / `success` / `page` / `page_size` 维度过滤：

```bash
# 只看失败
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7009/v1/admin/call-logs?success=false&page_size=50"

# 按渠道 + 时间窗（channel: api / openai / embed / internal …）
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7009/v1/admin/call-logs?channel=api&since=2026-05-01T00:00:00Z"

# 单条详情含 spans + payload；按 request_id 取完整嵌套 observation 树
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7009/v1/admin/call-logs/{id}"
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:7009/v1/admin/call-logs/{request_id}/tree"
```

### 清理（TTL）

`config/chameleon.json` 已有 `call_log.retention_days`（默认 `null` = 不自动清）。手动清旧 call_logs：

```sql
DELETE FROM call_logs WHERE created_at < NOW() - INTERVAL '90 days';
```

## 健康探针

```bash
GET /health    → 200 {"ok": true}                       —— 进程存活
GET /ready     → 200 {"data":{"db":true,"pgvector":true}}  —— DB 可达 + 扩展就位
                 503 当 DB 挂
```

适合接入 K8s livenessProbe / readinessProbe。

## 故障排查

| 症状 | 检查 |
|---|---|
| 启动 fail-fast | 看 startup log；常见 Redis 不通、`production` 缺 `CHAMELEON_CRYPTO_KEY` / `CHAMELEON_JWT_SECRET`、`${env:X}` 未设、agents.yaml 引用未注册 provider |
| KB 上传失败但服务能起 | MinIO 不可达（lifespan 只 warn 不 fail）；查 `component.json` 的 `minio.*` 与凭据 |
| invoke 返 60020 | provider 不可达（Dify / FastGPT 实例挂、网络断、超时） |
| invoke 返 60030 | provider 鉴权失败（外部 agent key 错 / 被吊销） |
| ingest task 卡 queued | 看 chameleon.log 里的 worker 日志；可能 embedding 503 / DB 锁 |
| SSE 立刻断 | Nginx 缓冲？看 `POST /v1/invoke` 等流式端点响应头有无 `X-Accel-Buffering: no` |
| `Event loop is closed` | 测试场景的 asyncpg 跨 loop 问题；pyproject 已设 session-scoped loop |

错误码段位以代码为准（见 `chameleon-core` 异常定义与全局异常 handler）。
