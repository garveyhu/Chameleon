# Chameleon 运维手册

## 部署模型

Chameleon v1 是单进程 FastAPI app。生产部署：

- 1×（或更多）uvicorn worker 跑 `chameleon.app.main:app`
- 依赖 1 个共享 PostgreSQL 16+pgvector 实例（不另起；复用 `/Users/links/Environment/Docker/postgres/`）
- 异步 ingest worker 与 web worker 同进程（FastAPI lifespan 内 `asyncio.create_task` 派发）

## 环境变量清单

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | `postgresql+asyncpg://user:pwd@host:port/chameleon` |
| `LOG_LEVEL` | | INFO | DEBUG / INFO / WARNING / ERROR |
| `CHAMELEON_INSTANCE_ID` | | 0 | 多实例部署时区分（雪花 ID 用） |
| `CHAMELEON_ROOT` | | 相对推算 | Docker 中指向项目根 |
| `CHAMELEON_DATA` | | `$ROOT/resources` | 数据目录 |
| `CHAMELEON_LOG_DIR` | | `$ROOT/logs` | 日志目录 |
| `REDIS_URL` | | — | v1 未使用，预留 |
| LLM `*_API_KEY` | 按需 | — | 与 `config/model.json` 里 `providers.*.key_env` 对应 |
| 外部 agent `*_KEY` | 按需 | — | 与 `config/agents.yaml` 里 `api_key_env` 对应 |

详见 [config/example/.env.example](../config/example/.env.example)。

## 起服务

### 开发模式

```bash
uv run uvicorn chameleon.app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后日志会显示已注册的 providers 和 agents：

```
─── Chameleon Registry ───
Loaded 3 providers: dify, fastgpt, langgraph
Loaded N agents:
  [langgraph] echo                       (built-in)
  [dify     ] customer-faq               (from agents.yaml)
  ...
```

### 生产模式（裸 uvicorn）

```bash
uv run uvicorn chameleon.app.main:app \
  --host 0.0.0.0 --port 8000 \
  --workers 4 \
  --proxy-headers --forwarded-allow-ips='*'
```

### 反向代理（Nginx）SSE 配置

⚠️ Nginx 默认会缓冲响应——必须为 `/v1/agents/*/invoke` 关掉缓冲，否则流式不流。

Chameleon 已在响应头加 `X-Accel-Buffering: no`，Nginx 1.5.6+ 会识别。也可显式配置：

```nginx
location /v1/agents/ {
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

`alembic.ini` 的 `sqlalchemy.url` 留空——`migrations/env.py` 从 `DATABASE_URL` 环境变量读。

### 红线（严格遵守）

1. **已发布的 migration 脚本绝不再改**（checksum 跑挂）
2. 新增 migration 必带 `--rollback` / `downgrade()`
3. pgvector 维度若改（v1 锁 1536）→ **新 migration + 老数据 re-embed**，不能 in-place ALTER
4. 大表加列加索引前评估锁影响（HNSW 索引建索引慢 + 占内存）
5. 不在 migration 里调 ORM 类（migration 是 schema 的快照，ORM 是当前态——分离）

### 现有 migration

```
0001_enable_pgvector       —— CREATE EXTENSION vector
0002_initial_tables        —— 8 张业务表 + HNSW(cosine, m=16, ef_construction=64)
```

## 备份与恢复

### 备份

```bash
# 只备 chameleon 库（不动 wave_obs 等共享实例的其它库）
docker exec postgres pg_dump -U collector -d chameleon -Fc \
  > backups/chameleon-$(date +%Y%m%d-%H%M%S).dump
```

**估算 chunks 表大小**：每个 chunk ≈ `(1536 * 4 bytes) + len(content) + meta`。
即 ≈ **6KB / chunk**（v1 1536 维 float32）。
1 万 chunks ≈ 60MB；100 万 ≈ 6GB。

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

## 升级（v0.1 → v0.2 流程）

```bash
# 1. 备份
docker exec postgres pg_dump -U collector -d chameleon -Fc > backups/before-v0.2.dump

# 2. 拉新代码
git pull
uv sync --all-packages

# 3. 看新 migration
uv run alembic history
uv run alembic upgrade head

# 4. 重启
# kill 老的 uvicorn，启动新的
```

## 调用审计

```bash
# 用 admin key 查
curl -H "Authorization: Bearer $ADMIN_KEY" \
  "http://localhost:8000/v1/admin/call-logs?success=false&page_size=50"

# 按 app + 时间窗
curl -H "Authorization: Bearer $ADMIN_KEY" \
  "http://localhost:8000/v1/admin/call-logs?app_id=my-app&since=2026-05-01T00:00:00Z"
```

### 清理（v1 暂不自动 TTL）

如需清旧 call_logs：

```sql
DELETE FROM call_logs WHERE created_at < NOW() - INTERVAL '90 days';
```

未来 v0.2 可加 `chameleon.json` 的 `call_log.retention_days` + 定时任务。

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
| 启动 fail-fast | 看 startup log；常见 `${env:X}` 未设、agents.yaml 引用未注册 provider |
| invoke 返 60020 | provider 不可达（DIFY/FastGPT 实例挂、网络断） |
| invoke 返 60030 | API key 错或被吊销 |
| ingest task 卡 queued | 看 chameleon.log 里的 worker 日志；可能 embedding 503 / DB 锁 |
| SSE 立刻断 | Nginx 缓冲？看响应头有无 `X-Accel-Buffering: no` |
| `Event loop is closed` | 测试场景的 asyncpg 跨 loop 问题；pyproject 已设 session-scoped loop |

详细错误码段位见 [设计文档 S3.6](plans/2026-05-20-chameleon-design.md#s36-错误码（五位段位）)。
