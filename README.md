# Chameleon

> 个人 AI 中枢应用——任何外部应用通过统一 HTTP API 接入 AI 能力，无需自带 LangGraph/SDK。

**v0.1.0** · Python 3.12+ · FastAPI · PostgreSQL + pgvector

## 定位

Chameleon 是 links 的"AI 飞轮"——把所有 AI 智能体作为可积累、可复用的资产管理。

三类 agent 来源（可扩展到第 N 种）：

- **本地 LangGraph 编排**（in-process）
- **DIFY 开发者 API**（HTTP 外调）
- **FastGPT 开发者 API**（HTTP 外调）

对外只露**一套**契约：`POST /v1/agents/{key}/invoke`（非流 + SSE），底层 provider 对客户端透明。

## 技术栈

| 层            | 选型                                                             |
| ------------- | ---------------------------------------------------------------- |
| 语言 / 运行时 | Python 3.12 + uv workspace 多包                                  |
| Web           | FastAPI + StreamingResponse SSE                                  |
| ORM           | SQLAlchemy 2.0 async（**单栈，禁用 SQLModel/Tortoise/raw SQL**） |
| DB            | PostgreSQL 16 + pgvector + HNSW                                  |
| 配置          | pydantic-settings (.env) + JSON 主题文件                         |
| 日志          | loguru（双 sink + 接管 stdlib logging）                          |
| 测试          | pytest + pytest-asyncio + respx + httpx                          |
| Lint          | ruff（含 isort）                                                 |

## 5 分钟 quickstart

### 0. 前置依赖

- macOS / Linux
- `uv >= 0.10`，Docker
- 本机共享 PG 实例（参考 `/Users/links/Environment/Docker/postgres/README.md`）
  - 镜像必须含 pgvector：`pgvector/pgvector:pg16`
  - 端口 `127.0.0.1:8103`，user `collector`

### 1. clone + 装依赖

```bash
git clone <repo> Chameleon && cd Chameleon/backend
uv sync --all-packages
```

> 后端所有命令都在 `Chameleon/backend/` 下执行；`Chameleon/frontend/` 为前端项目（待实现）。

### 2. 准备 PG（首次部署）

```bash
# 升级共享 PG 镜像（若尚未升级）
cd /Users/links/Environment/Docker/postgres
# docker-compose.yml: image: postgres:16-alpine → image: pgvector/pgvector:pg16
docker compose down && docker compose up -d

# 建 chameleon 库
docker exec postgres psql -U collector -d postgres \
  -c "CREATE DATABASE chameleon OWNER collector;"

# 应用迁移
cd <Chameleon repo>/backend
uv run alembic upgrade head
```

### 3. 拷配置（可选——example 已含合理默认）

```bash
# 在 backend/ 下
cp config/example/.env.example config/.env
cp config/example/chameleon.example.json config/chameleon.json
cp config/example/model.example.json config/model.json
cp config/example/agents.example.yaml config/agents.yaml
# 编辑 config/.env 加 OPENAI_API_KEY 等
```

### 4. 落第一个 admin key

```bash
uv run chameleon init-admin --name "your-name"
# 输出：✓ Admin API key created
#       KEY (仅一次回显，请立即保存)：chm_xxxxxxxxxxxxxxxxx
```

### 5. 起服务 + 第一个 curl

```bash
uv run uvicorn chameleon.app.main:app --host 0.0.0.0 --port 7009
```

在另一个终端：

```bash
# 健康检查
curl http://localhost:7009/ready

# 用 admin key 给应用发普通 key
ADMIN_KEY="chm_xxx..."
curl -X POST http://localhost:7009/v1/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"my-side-project","name":"My App","scopes":[]}'

# 用普通 key 调内置 echo agent
APP_KEY="chm_yyy..."
curl -X POST http://localhost:7009/v1/agents/echo/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"hello","stream":false}'
```

流式（SSE）：

```bash
curl -N -X POST http://localhost:7009/v1/agents/echo/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"流式回显","stream":true}'
```

## 项目结构

```
Chameleon/                              ← 前后端 monorepo 根
├── backend/                            ← uv workspace 根（Python 后端）
│   ├── chameleon-core/                 ← 基础设施 + AI infra + 共享 ORM
│   │   └── src/chameleon/core/
│   │       ├── infra/                  ← 运行时基础设施（db / logger / auth）
│   │       ├── api/                    ← API 契约层（Result[T] + 业务异常体系）
│   │       ├── config/                 ← 配置加载（pydantic-settings + inventory）
│   │       ├── models/                 ← 共享 ORM
│   │       ├── components/             ← AI 工具箱（llms / embeddings / vector / cache / knowledge）
│   │       ├── base/                   ← agent 抽象（BaseAgent + bridges）
│   │       ├── function/               ← prompt 模板 + Runnable 工厂占位
│   │       └── utils/                  ← 通用工具
│   ├── chameleon-providers/            ← Provider 适配层（**对写 agent 的人透明**）
│   │   ├── base/ local/ dify/ fastgpt/
│   ├── chameleon-agents/               ← 本地 agent 资产（**你的 AI 飞轮**）
│   │   ├── qwen_chat/                  ← 业务级 agent（直接可用）
│   │   └── examples/                   ← 三种范式样板（langgraph / runnable / native）
│   ├── chameleon-api/                  ← ★ 对外 AI 服务能力（业务方调）
│   │   └── src/chameleon/api/
│   │       └── agent/ knowledge/ conversation/ task/
│   ├── chameleon-system/               ← ★ 内部管理接口（前端 admin 面板调）
│   │   └── src/chameleon/system/
│   │       └── api_key/ admin/
│   ├── chameleon-app/                  ← FastAPI 启动器（薄：仅 lifespan + 中间件 + 装配）
│   │   └── src/chameleon/app/
│   │       └── main.py / cli.py
│   ├── config/                         ← 配置（实例已 gitignore，example 在 example/）
│   ├── migrations/                     ← Alembic（formatted SQL）
│   ├── tests/                          ← 跨包集成测试（E2E）
│   └── pyproject.toml                  ← workspace 配置
├── frontend/                           ← React + Vite + TS + Tailwind 管理面板（待实现）
├── docs/
│   ├── plans/                          ← v0.1 设计稿 + 实施计划 + 验收报告
│   ├── providers.md                    ← Provider 适配层原理 + 接入新平台
│   ├── extension-guide.md / operations.md / cli.md
│   └── getting-started.md              ← 入门指南
└── README.md
```

### 后端三层包定位

- **`chameleon-api/`** — 对外 AI 服务能力。业务方应用直调，前缀 `/v1/{agents,knowledge,conversations,tasks}`。**这个包是 Chameleon 的"能力清单"**：读完它的 router 就知道平台对外提供什么。
- **`chameleon-system/`** — 内部管理接口。前端管理面板专用，前缀 `/v1/admin/*`，需要 admin scope 鉴权。
- **`chameleon-app/`** — 启动器。把 `chameleon-api` + `chameleon-system` 的 router 装配到 FastAPI，挂中间件 / 全局异常 handler / lifespan，不含任何业务逻辑。

## 文档

> 👉 **第一次看？先读 [入门指南](docs/getting-started.md)**——用大白话讲每个模块干嘛 / 三种 agent 怎么接入 / 我的应用怎么调 / sage 用户友好

- 🌱 [**入门指南**](docs/getting-started.md) **← 使用者视角**
- 📐 [设计文档](docs/plans/2026-05-20-chameleon-design.md) ——核心决策与架构
- 🛠️ [实施计划](docs/plans/2026-05-20-chameleon-impl-plan.md)
- 🚀 [部署运维](docs/operations.md)
- ⚡ [CLI 指南](docs/cli.md)
- 🧩 [扩展指南](docs/extension-guide.md) ——加 agent / vector store / 业务模块
- 🔌 [Provider 适配层](docs/providers.md) ——agent 执行抽象层的原理 + 接入新平台 step
- ✅ [v1 验收报告](docs/plans/2026-05-20-chameleon-v1-acceptance-report.md)

## API 速查

| 端点                                    | 用途                               |
| --------------------------------------- | ---------------------------------- |
| `POST /v1/agents/{key}/invoke`          | **核心**：调用 agent（非流 / SSE） |
| `GET  /v1/agents` / `/{key}`            | 列出 / 详情                        |
| `GET  /v1/conversations[/{sid}]`        | 会话                               |
| `GET  /v1/conversations/{sid}/messages` | 历史                               |
| `POST /v1/conversations/{sid}/delete`   | 软删                               |
| `POST /v1/knowledge` 等                 | 知识库 CRUD + ingest + search      |
| `GET  /v1/tasks/{id}`                   | 异步任务进度                       |
| `POST /v1/admin/api-keys`               | 管理 key（admin scope）            |
| `GET  /v1/admin/call-logs`              | 调用审计                           |
| `GET  /health` / `/ready`               | 探针                               |

详见 [设计文档 S3](docs/plans/2026-05-20-chameleon-design.md#s3-对外-api-契约)。

## 开发

```bash
# 跑所有测试
uv run pytest -q

# lint + format
uv run ruff check . && uv run ruff format .

# 加新 migration
uv run alembic revision --autogenerate -m "add xxx"
uv run alembic upgrade head
```

## 协作

Co-authored with Claude Opus 4.7（1M context）. 设计与实施全程对话见 [docs/plans/](docs/plans/)。

## License

Personal use. Not for redistribution.
