# Chameleon v1 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal**：基于已确认的 `2026-05-20-chameleon-design.md`，把 Chameleon 从空目录推进到 v1 验收清单全过——一个可启动、可注册三类 agent、能跑通调用 / 会话 / 知识库 / 流式 / 异步 ingest 全链路的个人 AI 中枢。

**Architecture**：uv workspace 多包（5 个顶级单元：core / providers-base / 三类 provider / agents / app）+ FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL + pgvector + loguru + ruff。所有对外契约 `/v1/...` 统一 `Result[T]` 响应。

**Tech Stack**：Python 3.12+ / uv / FastAPI / SQLAlchemy 2.0(async) / Alembic / pydantic-settings / pydantic v2 / loguru / ruff / pytest+pytest-asyncio / httpx / PostgreSQL + pgvector / LangGraph

---

## 阅读约定

- **设计文档 = SoT（Source of Truth）**：`docs/plans/2026-05-20-chameleon-design.md`。所有 Task 的 "输入" 都隐含包含"此前所有已完成 Task 的产物 + 设计文档对应章节"。
- **每个 Task 颗粒度 ≈ 0.5–1 工作日**（不是 2-5 分钟微步）。Task 内部由开发者再分原子步。
- **代码不在本计划里**：本计划只指定**做什么、放哪、判断什么、做完怎么验**。代码细节在执行时按设计文档 + 规约现写。
- **规约红线**：始终遵守 `~/.claude/rules/python-codebase.md`（API 不写 SQL、Service 不返 ORM、统一 `Result[T]`、loguru `{}` 占位、ruff 通过等）。

---

## Phase 依赖图

```
P0 脚手架
  ↓
P1 chameleon-core 基础设施
  ↓
P2 Provider 抽象 + 三类 provider 子包
  ↓
P3 业务模块骨架（非流路径）
  ├──→ P4 SSE 流式
  └──→ P5 向量与知识库
            ↓
        P6 端到端冒烟（含 echo agent）
            ↓
        P7 文档 + v1 验收
```

P4 与 P5 可并行（互不依赖），但都依赖 P3。

---

## 关键全局歧义点与裁决原则

执行时遇到含糊地带按这些原则裁决，**不再回头追问用户**。

| # | 歧义点 | 裁决原则 |
|---|---|---|
| A1 | `agents.yaml` 占位符 `${baseurl:x}` / `${env:X}` 的实现细节 | yaml 解析后递归遍历，对每个 string value 跑统一正则替换；未找到变量 → 启动 fail-fast（不是静默 None） |
| A2 | `chameleon-app` 是否显式依赖每个具体 provider 子包 | v1 显式依赖三个（providers-base + langgraph + dify + fastgpt），未来按需启用切 `dependency-groups`。namespace 扫描负责"自动发现已安装的 provider" |
| A3 | 流式过程中已 yield 多个 `delta` 但 provider 抛错 | error event 后**不 append assistant 残骸消息**；user msg 已写在 ⑥ 之前，下次客户端可基于已落库 user msg 重试 |
| A4 | `build_graph()` 是 sync 还是 async | sync function（与 LangGraph 主流构造方式一致）。builder.py 内部缓存编译产物；async 调用走 `graph.astream_events` |
| A5 | 共享 ORM 在 core 后，业务 service 是否还要 thin repository 层 | 不要。modules service 直接 import core models 操作，ORM 即数据访问语言，不引额外抽象层 |
| A6 | Alembic env.py 怎么发现所有 ORM 模型 | `chameleon-core/src/chameleon/core/models/__init__.py` 统一 re-export 所有 model；Alembic `env.py` 仅 `from chameleon.core.models import Base` |
| A7 | API key 撤销 vs 真删 | v1 仅软撤（`revoked_at`），不暴露真删接口；DB 直连清理是管理员特权 |
| A8 | provider 子包 export `PROVIDER` 是实例还是类 | **实例**（registry 直接拿）。LangGraphProvider 内含 graph 缓存，实例即单例，无并发隐患（缓存写一次 + 读多次） |
| A9 | core/llm 是否抽象多厂商接口 | v1 只支持 **OpenAI 兼容协议**（OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 都走 OpenAI client），用 baseurl + key 区分；非兼容厂商出现再加 adapter |
| A10 | `input: list[Message]` 时当前轮 user msg 是否落库 | **落**（保证 messages 表完整 + call_log 可追溯）；但 `list[:-1]` 历史**仅在内存用作 history**，不落库（客户端自管的） |
| A11 | 雪花 ID 实现 | 用 `python-snowflake-id` 或自实现 64-bit；instance/machine id 取自 `CHAMELEON_INSTANCE_ID` env（默认 0）。session_id 字符串格式 = `"sess_" + base32(snowflake)` |
| A12 | API key 明文长度与前缀 | 明文 `chm_` + 40 字符 base62；`key_hash` = sha256(plaintext)；`key_prefix` 存前 12 字符（含 `chm_`）回显 |
| A13 | pgvector 索引选 HNSW vs IVFFlat | v1 用 **HNSW**（建索引慢但查询好、数据量小、个人项目零调参）。`m=16, ef_construction=64, vector_cosine_ops` |
| A14 | DIFY chat-messages vs workflows/run 路由 | 看 `AgentDef.config.mode`（`chat` / `workflow`）；DifyProvider 内部 if-else 走两条路径，都走统一 stream 解析 |
| A15 | FastGPT chatId 与 session_id 映射 | 同 DIFY 双写规则（`provider_conv_id` 字段），首轮 provider 返回后 service 落库 |

---

# Phase 0：Workspace 脚手架

**Goal**：把空目录变成"能 `uv sync` 通过 + 能起 FastAPI + 能连 PG + 能跑空 Alembic migration"的可运行壳。

**Output**：所有顶级子包目录就位、`uvicorn chameleon.app.main:app` 起得来、`curl localhost:8000/healthz` 通、PG + pgvector 容器跑起来、Alembic baseline migration 落地。

**估时**：1.5 天。

---

### Task 0.1 - 根 workspace pyproject + 工具链配置

**输入**：设计文档 S1.1（目录树）、`~/.claude/rules/python-codebase.md`（工具链段）

**输出**：
- `pyproject.toml`（根，含 `[tool.uv.workspace] members = ["chameleon-core", "chameleon-providers/*", "chameleon-agents/*", "chameleon-app"]`）
- `pyproject.toml` 内 ruff 配置（line-length=88、target-version=py312、`extend-select=["I"]`、isort section-order）
- `pyproject.toml` 内 pytest 配置（`asyncio_mode="auto"`、`testpaths=["tests"]`）
- `.python-version`（写 `3.12`）
- `uv.lock`（首次 `uv sync` 生成）

**关键决策点**：
- 根 pyproject 不声明任何包名 / version，仅作 workspace 容器（设 `[tool.uv.workspace]` + `[tool.ruff.*]` + `[tool.pytest.ini_options]`）
- 全局开发依赖（ruff / pytest / pytest-asyncio / mypy-可选 / httpx 测试用）放 `[dependency-groups]` 的 `dev`

**验收**：
```
uv sync --all-packages          # 成功
ruff check .                    # 通过（空仓库无文件）
```

---

### Task 0.2 - 五大子包目录骨架

**输入**：设计文档 S1.1、S1.2

**输出**：以下目录与最小 `pyproject.toml` + 空 `src/chameleon/<sub>/__init__.py`（PEP 420 namespace，**不放 `__init__.py` 在 `chameleon/` 这一层**）：

```
chameleon-core/pyproject.toml
chameleon-core/src/chameleon/core/__init__.py

chameleon-providers/base/pyproject.toml
chameleon-providers/base/src/chameleon/providers/base/__init__.py

chameleon-providers/langgraph/pyproject.toml
chameleon-providers/langgraph/src/chameleon/providers/langgraph/__init__.py

chameleon-providers/dify/pyproject.toml
chameleon-providers/dify/src/chameleon/providers/dify/__init__.py

chameleon-providers/fastgpt/pyproject.toml
chameleon-providers/fastgpt/src/chameleon/providers/fastgpt/__init__.py

chameleon-agents/echo/pyproject.toml
chameleon-agents/echo/src/chameleon/agents/echo/__init__.py

chameleon-app/pyproject.toml
chameleon-app/src/chameleon/app/__init__.py
chameleon-app/src/chameleon/app/main.py            # FastAPI app
```

**关键决策点**：
- 每个子包 `pyproject.toml` 用 hatch（`build-backend = "hatchling.build"`）或 `uv build`；hatchling 是 uv workspace 主流，选它
- distribution 名前缀 `chameleon-*`（依设计文档 S1 锁定）：`chameleon-core`、`chameleon-providers-base`、`chameleon-provider-langgraph`、`chameleon-provider-dify`、`chameleon-provider-fastgpt`、`chameleon-agent-echo`、`chameleon-app`
- 依赖关系按 S1.2 铁律连：core → providers-base → 具体 provider → app；agent 只依赖 core
- `chameleon-app` 显式声明 4 个 provider 依赖（裁决 A2）

**验收**：
```
uv sync --all-packages          # 成功，全部 editable install
python -c "import chameleon.core; import chameleon.providers.base; import chameleon.providers.langgraph; import chameleon.providers.dify; import chameleon.providers.fastgpt; import chameleon.agents.echo; import chameleon.app"
# 全部 import 成功，无错
```

---

### Task 0.3 - PG + pgvector 容器 + Alembic 初始化

**输入**：设计文档 S4.1（schema 整体）、S4.2（pgvector 决策）、A13

**输出**：
- `docker-compose.yml`（postgres:16 + pgvector 扩展、暴露 5432、数据卷）
- `migrations/`（Alembic init 产物：`alembic.ini` 移到根、`migrations/env.py`、`migrations/versions/`）
- 第一个 baseline migration（仅 `CREATE EXTENSION IF NOT EXISTS vector`，无表）
- `config/example/.env.example` 加 `DATABASE_URL` 示例

**关键决策点**：
- Postgres 镜像选 `pgvector/pgvector:pg16`（官方）而非 `postgres:16` + 手动装扩展
- Alembic 用 async 模式（`env.py` 用 `async_engine_from_config`）
- baseline migration 名字 `0001_enable_pgvector.py`，含 `--rollback DROP EXTENSION vector`

**验收**：
```
docker compose up -d pg
psql $DATABASE_URL -c "SELECT extname FROM pg_extension WHERE extname='vector';"
# → vector

alembic upgrade head
# → 0001_enable_pgvector.py 应用成功
```

---

### Task 0.4 - 最小 FastAPI app + /healthz + /readyz

**输入**：设计文档 S3.1、S3.3 健康段

**输出**：
- `chameleon-app/src/chameleon/app/main.py`：FastAPI app 初始化、`/healthz` 返 `{"ok": true}`、`/readyz` 检 DB（用 chameleon-core 的 db.py，本阶段用最简单 `SELECT 1`）
- 暂不接入 auth、不接入 router、不接入 registry——只让壳跑起来

**关键决策点**：
- `/healthz` **不**走 `/v1` 前缀（运维 probe 友好）
- `/readyz` 失败返 503，body 仍是 `Result.fail(...)`（响应封装从 Phase 1 加，此阶段先返 dict 占位，P1 接入后替换）

**验收**：
```
uvicorn chameleon.app.main:app --port 8000 &
curl -s http://localhost:8000/healthz | jq .
# → {"ok": true}
curl -s http://localhost:8000/readyz | jq .
# → DB 检查通过的响应
```

---

### Task 0.5 - Phase 0 集成验收 + commit

**输入**：T0.1-T0.4 全部产物

**输出**：
- 全部 `uv sync` 通过
- 全部 `ruff check .` 通过
- 单元测试占位（每个子包至少一个 `tests/test_smoke.py` 验 import）
- commit：`chore(scaffold): 建立 uv workspace 骨架与最小 FastAPI 壳`

**验收**：
```
uv sync --all-packages && ruff check . && pytest -q
# 全绿
```

---

# Phase 1：chameleon-core 基础设施

**Goal**：把所有"业务模块和 agent 都要靠"的地基铺好——配置、日志、DB、响应封装、异常体系、鉴权、共享 ORM 模型。

**Output**：可以在任何子包里 `from chameleon.core.config import inventory as cfg`、`from chameleon.core.db import get_session`、`from chameleon.core.models import Conversation, ApiKey`，且 `chameleon-app` 已挂全局异常 handler、auth middleware。

**估时**：3.5 天。

---

### Task 1.1 - config 子系统

**输入**：设计文档 S5（整章）

**输出**：
- `chameleon-core/src/chameleon/core/config/__init__.py` — export 全局实例：`env_settings`, `chameleon_settings`, `url_settings`, `model_settings`, `inventory`
- `constants.py` — `CHAMELEON_ROOT` / `CONFIG_PATH` / `DATA_ROOT` / `LOG_DIR`，env 优先 + 相对路径推算 fallback
- `base_settings.py` — 学 sage 的 BaseSettings（点路径 get/set + `from_json`/`from_yaml`/`from_env` 类方法）+ `${baseurl:x}` / `${env:X}` 占位符替换工具函数
- `env_settings.py` — pydantic-settings 子类，绑 `.env`，含 `DATABASE_URL`（PostgresDsn）、`REDIS_URL`（可选）、`LOG_LEVEL`、各种 `*_API_KEY: SecretStr | None`
- `json_settings.py` — `ChameleonSettings` / `URLSettings` / `ModelSettings` 类（三个 BaseSettings 子类，每个绑自己的 JSON 文件）+ 全局实例化
- `inventory.py` — 具名 getter（`case_llm()`, `kb_default_top_k()`, `session_history_limit()`, `database_url()` 等，详见设计文档 S5.3）

**关键决策点**：
- A1：占位符替换在 `BaseSettings.from_yaml` 时**递归**遍历所有 dict / list / str；变量未找到 → 抛 `ConfigError`，启动 fail-fast
- 只给 getter，无 setter（裁决：运行时不可变）
- `EnvSettings` 用 `model_config = SettingsConfigDict(env_file=CONFIG_PATH/".env", extra="ignore")`

**验收**：
```
# 在 tests/test_config.py 写：
def test_inventory_loads():
    from chameleon.core.config import inventory as cfg
    assert cfg.database_url().startswith("postgresql")
    assert cfg.session_history_limit() == 20

pytest chameleon-core/tests/test_config.py -v
# 通过
```

---

### Task 1.2 - example 配置文件全套

**输入**：设计文档 S5.2

**输出**：`config/example/` 下：
- `chameleon.example.json`
- `baseurl.example.json`
- `model.example.json`
- `agents.example.yaml`
- `.env.example`

每个文件按设计文档 S5.2 的示例填充（敏感值用占位 `sk-xxx`、`change-me`、`localhost`）。

**关键决策点**：
- example 文件**进 git**（让新部署能直接 cp 改）
- 真实 `.env`、`chameleon.json`、`model.json`、`agents.yaml` 已在 `.gitignore`

**验收**：
```
ls config/example/
# 5 个 example 文件就位

cp config/example/.env.example config/.env
cp config/example/chameleon.example.json config/chameleon.json
cp config/example/baseurl.example.json config/baseurl.json
cp config/example/model.example.json config/model.json
cp config/example/agents.example.yaml config/agents.yaml
# 编辑 .env 改 DATABASE_URL 为本地 PG

uv run python -c "from chameleon.core.config import inventory as cfg; print(cfg.case_llm())"
# 打印 example 里配的 llm 名（如 qwen-plus）
```

---

### Task 1.3 - logger（loguru）

**输入**：`~/.claude/rules/python-codebase.md` 日志段

**输出**：
- `chameleon-core/src/chameleon/core/logger.py`
- 双 sink：stdout（彩色，dev 友好）+ 文件（`LOG_DIR/chameleon.log`，rotation 50MB / 7 day）
- 全局 logger 配置函数 `setup_logger()`，在 chameleon-app/main.py 启动时调用
- log_level 取自 `inventory.log_level()`（默认 INFO）

**关键决策点**：
- 强制 `{}` 占位符（loguru 默认）—— 在 README 写明，不允许 `f"..."` 当参数
- 错误日志必带 `logger.exception()`（含堆栈）
- 在 chameleon-app/main.py 启动时 `setup_logger()`，移除 uvicorn 默认 logger handler 避免重复

**验收**：
```
uvicorn chameleon.app.main:app --port 8000
# 启动日志出现 loguru 格式（带时间 + 级别 + 文件位置）
ls logs/
# chameleon.log 存在
```

---

### Task 1.4 - response.py + exceptions.py

**输入**：设计文档 S3.4（响应封装）、S3.6（错误码）

**输出**：
- `chameleon-core/src/chameleon/core/response.py`：`Result[T]` 学 sage（`success/code/message/data` + classmethod `ok()` / `fail()`）+ `PageParams` + `PageResult[T]`
- `chameleon-core/src/chameleon/core/exceptions.py`：
  - `BusinessError(Exception)` 基类，含 `code: int` + `message: str`
  - 派生：`ValidationError`、`AuthError`、`NotFoundError`、`PermissionError`、`InternalError`、`RegistryError`
  - 错误码常量表（设计文档 S3.6 全套，封装为 `class ResultCode(Enum)`，学 sage）
- 全局异常 handler 函数（不在此 Task 注册，仅写好函数）

**关键决策点**：
- 错误码用 IntEnum 还是 dict？选 **IntEnum 子类**（既是 int 又有 message 属性，学 sage 的 ResultCode 风格）
- `Result.fail()` 接受 `code: int | ResultCode` 参数（兼容两种调用）
- `BusinessError.__init__(self, code: ResultCode | int, message: str | None = None)`，message 缺省时用 ResultCode 自带

**验收**：
```
# tests/test_response.py
def test_result_ok():
    r = Result.ok({"x": 1})
    assert r.success and r.code == 200 and r.data == {"x": 1}

def test_result_fail():
    r = Result.fail(ResultCode.AgentNotFound)
    assert not r.success and r.code == 40401

pytest chameleon-core/tests/test_response.py -v
# 通过
```

---

### Task 1.5 - db.py（async session 工厂）

**输入**：设计文档 S4（DB 整体）

**输出**：
- `chameleon-core/src/chameleon/core/db.py`：
  - `engine`（用 `inventory.database_url()` + `create_async_engine`，pool_size=10, pool_pre_ping=True）
  - `AsyncSessionLocal`（`async_sessionmaker`）
  - FastAPI Depends 函数 `get_session()` —— async generator，自动 commit/rollback
  - 全局 `Base = declarative_base()`（导出给 models/ 用）

**关键决策点**：
- driver 选 `asyncpg`（性能 + 原生 async）
- `expire_on_commit=False`（避免 commit 后 ORM 实例无法读字段）
- session 生命周期 = 一次 HTTP 请求；异常 → rollback；正常退出 → commit

**验收**：
```
# tests/test_db.py
async def test_db_connect(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1

pytest chameleon-core/tests/test_db.py -v
# 通过（需要 PG 容器跑起来）
```

---

### Task 1.6 - 共享 ORM 模型 + 第一批表的 Alembic migration

**输入**：设计文档 S4.1（核心表 7 张）、A6（Alembic 模型发现）

**输出**：
- `chameleon-core/src/chameleon/core/models/__init__.py` — re-export `Base`、`ApiKey`、`Conversation`、`Message`、`KnowledgeBase`、`Document`、`Chunk`、`CallLog`、`Task`
- `models/base.py` — `Base`、`TimestampMixin`（created_at / updated_at）、`SoftDeleteMixin`（deleted_at）、雪花 ID 生成器 + 默认值（裁决 A11）
- `models/api_key.py` — `ApiKey` 实体，按 S4.1 schema
- `models/conversation.py` — `Conversation` + `Message`，按 S4.1 schema
- `models/knowledge.py` — `KnowledgeBase` + `Document` + `Chunk`，**`Chunk.embedding` 用 sqlalchemy-pgvector 的 `Vector(1536)` 类型**
- `models/call_log.py` — `CallLog`
- `models/task.py` — `Task`
- `migrations/env.py` — `from chameleon.core.models import Base; target_metadata = Base.metadata`
- 新 migration `0002_initial_tables.py`（autogenerate，含所有表 + 索引 + HNSW 向量索引）

**关键决策点**：
- 雪花 ID 实现选 `python-snowflake-id` 或自封——选自封 helper（仅一份 `utils/snowflake.py`，instance id 取 env，方法 `next_id() -> int`）
- `Vector(1536)` 列：用 `pgvector.sqlalchemy.Vector`（pgvector 官方 Python 包）
- HNSW 索引创建用 `op.create_index(..., postgresql_using="hnsw", postgresql_with={"m": 16, "ef_construction": 64}, postgresql_ops={"embedding": "vector_cosine_ops"})`
- 所有 enum 字段（role / status / source_type）用 `String(16)` + 应用层枚举，**不用 PG 原生 ENUM**（迁移友好）
- 软删字段全部 `deleted_at TIMESTAMPTZ NULL`，查询用 `WHERE deleted_at IS NULL`（不引入 sqlalchemy 软删插件，自己写 Repository 函数控制）

**验收**：
```
alembic upgrade head
# 0002_initial_tables 应用成功
psql $DATABASE_URL -c "\d chunks"
# embedding 列类型 = vector(1536)
psql $DATABASE_URL -c "\di"
# 7 张表 + HNSW 索引就位

# tests/test_models.py
async def test_create_api_key(db_session):
    key = ApiKey(app_id="test", name="t", key_hash="h", key_prefix="chm_test", scopes=[])
    db_session.add(key)
    await db_session.flush()
    assert key.id > 0

pytest chameleon-core/tests/test_models.py -v
# 通过
```

---

### Task 1.7 - auth middleware + CurrentApp Depends

**输入**：设计文档 S3.2（鉴权）、A12（key 格式）

**输出**：
- `chameleon-core/src/chameleon/core/auth.py`：
  - `hash_api_key(plaintext: str) -> str`（sha256）
  - `generate_api_key() -> tuple[plaintext, hash, prefix]`（`chm_` + 40 字符 base62）
  - FastAPI Depends `current_app(...)` — 从 `Authorization: Bearer` 头取 → hash → 查 `api_keys`（未撤销）→ 返回 `CurrentApp(id, app_id, name, scopes)`；缺失抛 `MissingApiKey`，无效抛 `InvalidApiKey`，已撤抛 `ApiKeyRevoked`
  - Depends factory `require_scope(scope: str)` —— 返回一个 Depends，校验 `CurrentApp.scopes` 包含 scope（如 `require_scope("admin")`）

**关键决策点**：
- A12：plaintext 格式 `chm_` + 40 字符 base62（`secrets.token_urlsafe(30)` 截到 40 字符 + 强制前缀）
- `current_app` 顺路 `UPDATE api_keys SET last_used_at = now()` —— 用 background task 避免阻塞
- 不做内存缓存（v1 个人项目低 QPS，DB 查询不贵）；未来加 cache 时 wrap 这个函数即可

**验收**：
```
# tests/test_auth.py
def test_hash_idempotent():
    assert hash_api_key("chm_abc") == hash_api_key("chm_abc")

async def test_current_app_valid(client, db_session, fixture_api_key):
    plaintext, _ = fixture_api_key  # 已存 hash 到 DB
    r = await client.get("/v1/agents", headers={"Authorization": f"Bearer {plaintext}"})
    assert r.status_code == 200

async def test_current_app_revoked(client, fixture_revoked_key):
    r = await client.get("/v1/agents", headers={"Authorization": f"Bearer {fixture_revoked_key}"})
    assert r.json()["code"] == 40103

pytest chameleon-core/tests/test_auth.py -v
# 通过
```

---

### Task 1.8 - 全局异常 handler 注册 + main.py 整合

**输入**：设计文档 S3.6、Python 规约的"全局异常 handler"段

**输出**：
- `chameleon-app/src/chameleon/app/main.py`：
  - 启动时调 `setup_logger()`
  - 注册全局 exception handler：
    - `BusinessError` → `Result.fail(exc.code, exc.message)`，HTTP 400/401/403/404 由 code 推
    - `RequestValidationError` → `Result.fail(ResultCode.ValidationError, ...)`，HTTP 422
    - `Exception` 兜底 → `logger.exception(); Result.fail(ResultCode.InternalError, "服务异常，请稍后重试")`，HTTP 500
  - `X-Request-Id` middleware（如缺失则生成 uuid，回写 response header）
  - **本阶段还不挂业务 router**，仅 health 接口

**关键决策点**：
- handler 返回 `JSONResponse(content=result.model_dump(), status_code=...)`
- HTTP status 推断逻辑：code 段 401xx → 401；403xx → 403；404xx → 404；429xx → 429；5xxxx → 500；6xxxx → 502 / 504（provider 错走 502，timeout 走 504）；其余 → 400

**验收**：
```
# tests/test_global_handler.py
async def test_business_error(client):
    # 临时挂一个故意抛 BusinessError 的路由
    r = await client.get("/test/raise-not-found")
    assert r.status_code == 404
    assert r.json() == {"success": False, "code": 40401, "message": "...", "data": None}

async def test_validation_error(client):
    r = await client.post("/test/echo", json={"missing_required": True})
    assert r.status_code == 422
    assert r.json()["code"] == 40001

pytest chameleon-app/tests/test_global_handler.py -v
# 通过
```

---

### Task 1.9 - Phase 1 集成验收 + commit

**输入**：T1.1-T1.8 全部产物

**输出**：commit：`feat(core): 完成 chameleon-core 基础设施（config/logger/db/response/exceptions/auth/models）`

**验收**：
- `uv sync --all-packages && ruff check . && pytest -q` 全绿
- `alembic upgrade head` 成功
- `uvicorn chameleon.app.main:app` 起来，`/healthz`、`/readyz` 通

---

# Phase 2：Provider 抽象 + 三类 provider 子包

**Goal**：把 Chameleon 的"心脏"建好——所有 provider 都通过统一接口对话，langgraph 优先打通，dify/fastgpt 用 mock server 验证。

**Output**：启动时 registry 能扫到全部 provider + agent，全局 `PROVIDERS` / `AGENTS` 两个只读 dict 就位；LangGraphProvider 能加载 echo agent 的 build_graph 并跑通 stream（echo agent 在 Phase 6 写完整版，此阶段写最简占位）。

**估时**：3.5 天。

---

### Task 2.1 - chameleon-providers-base 完整

**输入**：设计文档 S2（整章）、A8

**输出**：
- `chameleon-providers/base/src/chameleon/providers/base/types.py`：
  - `Message`（role: Literal["user","assistant","system","tool"], content: str | dict）
  - `AgentDef`（pydantic BaseModel：key/provider/description/version/tags/config）
  - `StepRecord`、`Citation`、`ToolCallRecord`、`Usage`（pydantic BaseModel）
  - `InvokeContext`（pydantic BaseModel，按 S2.1）
  - `InvokeResult`（pydantic BaseModel）
  - `StreamEventType`（StrEnum：`delta/step/citation/tool_call/tool_result/metadata/done/error`）
  - `StreamEvent`（pydantic BaseModel：`type: StreamEventType, data: dict`）
- `protocol.py` — `class Provider(ABC)`，含 `name`, `stream()` ABC, `invoke()` 默认聚合实现, `healthcheck()` 默认返 True
- `errors.py` — `ProviderError` 基类 + 六个子类（按 S2.5）
- `registry.py` —
  - `build_provider_registry() -> dict[str, Provider]`（扫 `chameleon.providers.*` namespace，取 `PROVIDER`）
  - `build_agent_registry(provider_registry) -> dict[str, AgentDef]`（扫 `chameleon.agents.*` namespace + 读 `config/agents.yaml`，合并）
  - `init_registry()` — 启动钩子，组装两个全局 dict 并 fail-fast 检测重复 key
  - 全局 `PROVIDERS: dict[str, Provider]`、`AGENTS: dict[str, AgentDef]`（模块级，registry 构建后填充）

**关键决策点**：
- `Provider.invoke()` 默认实现：异步消费 `self.stream()`，收集所有 event，从 `done` event 的 data 构造 `InvokeResult`
- registry 用 `pkgutil.iter_modules` + `importlib.import_module` 扫描；agent 子包必须 `__init__.py` 顶层 export `AGENT_META` + `build_graph`
- A1 占位符替换在 `agents.yaml` 加载时完成
- registry 加载顺序：providers 先 → agents 后（agent 校验 provider 存在）

**验收**：
```
# tests/test_registry.py
def test_build_provider_registry(monkeypatch):
    providers = build_provider_registry()
    assert "langgraph" in providers
    assert "dify" in providers
    assert "fastgpt" in providers

def test_build_agent_registry_from_yaml(tmp_path, monkeypatch):
    yaml_text = """
- key: test-agent
  provider: dify
  description: test
  endpoint: http://localhost/v1
  app_id: app-x
  api_key_env: TEST_KEY
"""
    # 写到临时 agents.yaml，patch CONFIG_PATH，验证加载
    ...

pytest chameleon-providers/base/tests/test_registry.py -v
# 通过
```

---

### Task 2.2 - LangGraphProvider

**输入**：设计文档 S2.4（langgraph 段）、A4、A8

**输出**：
- `chameleon-providers/langgraph/pyproject.toml` — deps: `chameleon-core`, `chameleon-providers-base`, `langgraph>=0.2`
- `src/chameleon/providers/langgraph/__init__.py` — `from .provider import LangGraphProvider; PROVIDER = LangGraphProvider()`
- `provider.py` — `class LangGraphProvider(Provider)`：
  - `name = "langgraph"`
  - 持 `_graphs: dict[str, CompiledGraph]` 缓存
  - `stream(ctx)` — 拿 `ctx.agent_def.config["module"]` → `importlib.import_module` → `getattr(mod, build_fn)` → 构图（缓存 by agent_key）→ 用 `graph.astream_events` 跑 → 翻译事件
- `builder.py` — `get_or_build_graph(agent_def) -> CompiledGraph`，处理缓存 + lock 避免并发重复构建
- `stream.py` — `translate_langgraph_event(event) -> StreamEvent | None`：把 LangGraph 的 `astream_events` 输出（`on_chat_model_stream` / `on_tool_start` / `on_tool_end` / `on_chain_end`）映射成 StreamEvent

**关键决策点**：
- A4：`build_graph()` sync function，签名 `() -> CompiledGraph`
- graph 缓存：用 `asyncio.Lock` per agent_key 保护首次构建；缓存 hit 直接返回
- `astream_events(version="v2")` 是 LangGraph 推荐 API；按 `event["event"]` 字段分流
- `state` 注入：LangGraph 一般用 `MessagesState`，把 `ctx.history + [HumanMessage(ctx.input)]` 灌入

**验收**：
```
# tests/test_langgraph_provider.py
async def test_invoke_echo(monkeypatch):
    # mock 一个 build_graph 返回 echo graph
    ...
    provider = LangGraphProvider()
    ctx = InvokeContext(agent_def=mock_def, input="hi", history=[], session_id="s", app_id="a", stream=False)
    result = await provider.invoke(ctx)
    assert "hi" in result.answer

async def test_stream_yields_delta():
    ...
    events = [ev async for ev in provider.stream(ctx)]
    assert any(e.type == StreamEventType.delta for e in events)
    assert events[-1].type == StreamEventType.done

pytest chameleon-providers/langgraph/tests/ -v
# 通过
```

---

### Task 2.3 - DifyProvider

**输入**：设计文档 S2.4（dify 段）、A14、A15

**输出**：
- `chameleon-providers/dify/pyproject.toml` — deps: `chameleon-core`, `chameleon-providers-base`
- `client.py` — async HTTP client（基于 `httpx.AsyncClient`，封装超时 / 重试 / Authorization 头）
  - `chat_messages(endpoint, api_key, payload, stream=True)` → AsyncIterator[bytes]（SSE 原始字节）
  - `workflows_run(...)` 同上
- `stream.py` — `parse_dify_sse(line_iter) -> AsyncIterator[StreamEvent]`：
  - DIFY 事件：`message` → `delta`；`agent_thought` → `step(thinking=...)`；`node_started/node_finished` → `step`；`message_end` → `done`（带 usage）
- `provider.py` — `class DifyProvider(Provider)`：
  - `stream(ctx)` —
    - 从 `ctx.agent_def.config` 取 endpoint, app_id, api_key_env
    - 解析 `api_key_env` → `os.environ`
    - 按 `mode` 走 chat / workflow（裁决 A14）
    - 透传 `ctx.provider_conv_id`（裁决 A15）
    - 在 done event 把新 `conversation_id` 写入 event.data（service 层据此回写 DB）
- `__init__.py` — `PROVIDER = DifyProvider()`

**关键决策点**：
- httpx_mock / respx 做 unit test mock；fixtures 存 `tests/fixtures/dify_response_chat.sse`、`dify_response_workflow.sse`（真实抓包脱敏）
- 错误映射：DIFY 4xx → `ProviderInputError`；5xx → `ProviderInternalError`；超时 → `ProviderUnreachableError`；401/403 → `ProviderAuthError`
- 用 `httpx.AsyncClient` 的 `stream()` 上下文管理器，SSE 用 `aiter_lines()`

**验收**：
```
# tests/test_dify_provider.py
@respx.mock
async def test_dify_chat_stream():
    respx.post("...").mock(return_value=Response(200, text=fixture("dify_chat.sse")))
    provider = DifyProvider()
    events = [ev async for ev in provider.stream(ctx)]
    assert events[-1].type == StreamEventType.done
    assert events[-1].data["session_id"] == ctx.session_id

pytest chameleon-providers/dify/tests/ -v
# 通过
```

---

### Task 2.4 - FastGPTProvider

**输入**：设计文档 S2.4（fastgpt 段）、A15

**输出**：与 T2.3 同构：
- `chameleon-providers/fastgpt/` 完整子包
- `client.py` 调 `{endpoint}/v1/chat/completions`，OpenAI 兼容协议
- `stream.py` 解析 OpenAI delta（`choices[0].delta.content`）+ FastGPT 扩展（`responseData[*]` 含 flow node 信息）
- `provider.py` 双写 `chatId`

**关键决策点**：
- FastGPT stream 既走 OpenAI `[DONE]` 又有自定义 `data: {responseData: ...}` 行，需要分流处理
- `responseData` 数组里的 node 节点信息 → 翻成 `step` event
- 用 fixtures 跑 unit test（同 T2.3）

**验收**：同 T2.3 形式，`pytest chameleon-providers/fastgpt/tests/` 通过。

---

### Task 2.5 - registry 接入 main.py + 启动日志

**输入**：T2.1-T2.4 产物

**输出**：
- `chameleon-app/src/chameleon/app/main.py` 启动钩子：调 `init_registry()`，日志打印：
  ```
  Loaded 3 providers: langgraph, dify, fastgpt
  Loaded N agents:
    [langgraph] echo            (built-in)
    [dify     ] customer-faq    (from agents.yaml)
    [fastgpt  ] order-analyst   (from agents.yaml)
  ```
- 启动时调 `provider.healthcheck()` 异步触发（warn-only，不阻塞）

**关键决策点**：
- registry 构建失败（如 agents.yaml 占位变量未找到）→ fail-fast：日志 ERROR + `sys.exit(1)`
- 重复 agent key → fail-fast

**验收**：
```
uvicorn chameleon.app.main:app
# 日志显式列出所有加载的 provider 与 agent
```

---

### Task 2.6 - Phase 2 集成 + commit

**输出**：commit：`feat(providers): 完成 Provider 抽象与三类 provider 适配（langgraph/dify/fastgpt）`

**验收**：`pytest -q` 全绿，`uvicorn` 启动日志显示 registry 加载成功。

---

# Phase 3：业务模块骨架（非流路径）

**Goal**：把 agent 调用、会话、API key 三个核心业务模块的非流路径打通。客户端用 admin key 发普通 key，然后用普通 key 调 agent，会话自动签发，历史正确回放。

**Output**：所有 `/v1/admin/api-keys/*`、`/v1/agents/{key}/invoke`（非流）、`/v1/conversations/*` 路径可用并通过集成测试。

**估时**：3.5 天。

---

### Task 3.1 - modules/api_key 模块 + CLI init-admin

**输入**：设计文档 S3.2（鉴权）、S3.3 接口表（admin 段）、A7

**输出**：
- `chameleon-app/src/chameleon/app/modules/api_key/`
  - `schemas.py` — `CreateApiKeyRequest`、`ApiKeyItem`、`ApiKeyCreated`（含明文，仅在创建时回显）、`PageResult[ApiKeyItem]`
  - `service.py` — `create_api_key`、`list_api_keys`、`revoke_api_key`
  - `api.py` — `POST /v1/admin/api-keys`、`GET /v1/admin/api-keys`、`POST /v1/admin/api-keys/{id}/revoke`（全部 `Depends(require_scope("admin"))`）
- `chameleon-app/src/chameleon/app/cli.py` — 入口命令：
  - `chameleon init-admin --name <name>`：检查 `api_keys` 表是否已有 admin scope key，否则插入第一个 admin key（明文打印一次 + 警告）
  - `chameleon db upgrade`：执行 `alembic upgrade head` 的封装
  - CLI 入口通过 `[project.scripts] chameleon = "chameleon.app.cli:main"` 暴露

**关键决策点**：
- 创建 key 时返回 `ApiKeyCreated`，明文 `key` 字段**只在创建响应里出现一次**；后续列表只返 `key_prefix`
- `init-admin` 在 DB 已有 admin key 时拒绝执行（防误操作），用 `--force` 才允许多发
- A7：`POST /v1/admin/api-keys/{id}/revoke` 只设 `revoked_at`，不删行

**验收**：
```
chameleon init-admin --name links
# 输出：[Admin Key Created] key=chm_xxxxxx...  (only shown once)

curl -X POST localhost:8000/v1/admin/api-keys \
  -H "Authorization: Bearer chm_<admin>" \
  -d '{"app_id":"my-app","name":"My App","scopes":[]}'
# 返回 {"code":200, "data":{"key":"chm_xxxx", "key_prefix":"chm_xxxx12", ...}}

curl -X GET localhost:8000/v1/admin/api-keys \
  -H "Authorization: Bearer chm_<admin>"
# 返回列表，不含明文
```

---

### Task 3.2 - modules/conversation

**输入**：设计文档 S3.3 conversation 段、S4.3 数据流

**输出**：
- `chameleon-app/src/chameleon/app/modules/conversation/`
  - `schemas.py` — `ConversationItem`、`MessageItem`、`PageResult[...]`
  - `service.py`：
    - `create(session_id, agent_key, provider, app_id) -> Conversation`
    - `get(session_id) -> Conversation`（找不到抛 `ConversationNotFound`）
    - `load_messages(session_id, limit=N) -> list[Message]`（按 seq asc，取最新 N 条）
    - `append(session_id, role, content, **meta) -> Message`（自动 seq + 1）
    - `touch(session_id, **fields)`（last_message_at / title / provider_conv_id）
    - `soft_delete(session_id)`
  - `api.py` —
    - `GET /v1/conversations`（分页、按 app_id filter，admin 不限）
    - `GET /v1/conversations/{session_id}`
    - `GET /v1/conversations/{session_id}/messages`（分页）
    - `POST /v1/conversations/{session_id}/delete`

**关键决策点**：
- 普通 app key 只能看自己 app_id 的 conversations；admin scope 可看全量（service 层带 `current_app` 参数判断）
- `load_messages` 取最新 N 条但按时间正序返回（agent 拼接 history 需要时间顺序）
- `append` 内必须事务保护 seq 单调递增（用 `SELECT MAX(seq) ... FOR UPDATE` 或简单 `count + 1`，PG 自增 seq 会更稳——v1 简单版用 `count + 1`）

**验收**：
```
pytest chameleon-app/tests/modules/conversation/ -v
# 单元测试 + 集成测试（用 TestClient + 数据库 fixture）通过
```

---

### Task 3.3 - modules/agent 非流路径

**输入**：设计文档 S3.5（invoke 契约）、S4.3（端到端数据流）、A10

**输出**：
- `chameleon-app/src/chameleon/app/modules/agent/`
  - `schemas.py`：
    - `InvokeRequest`（`input: str | list[MessageInput]`, `session_id: str | None`, `stream: bool`, `context: dict`, `options: dict`）
    - `InvokeResponse`（`session_id, request_id, answer, steps, citations, tool_calls, usage`）
    - `MessageInput`（`role`, `content`）
    - `AgentItem`（GET /v1/agents 用）
  - `service.py`：
    - `list_agents() -> list[AgentItem]`（从 AGENTS 注册表读，不查 DB）
    - `get_agent(key) -> AgentItem | None`
    - `invoke(agent_key, request, current_app) -> InvokeResponse`：完整实现 S4.3 ①-⑨（非流分支）
      - 处理 input 双形态（A10）
      - 在调 provider 前落 user msg
      - 调 `PROVIDERS[provider].invoke(ctx)`（默认聚合实现）
      - 落 assistant msg
      - touch conversation（last_message_at, title 首轮）
      - 写 call_log
  - `api.py`：
    - `POST /v1/agents/{key}/invoke`（stream=false 路径，本 Task 实现；stream=true 在 P4 接）
    - `GET /v1/agents`、`GET /v1/agents/{key}`

**关键决策点**：
- A10：`input: list[Message]` 时仍落库当前轮 user msg（last message），history 仅在内存
- A3：流式失败处理在 P4 处理；非流式 provider 抛错 → BusinessError → 全局 handler 接管
- call_log 写入用 BackgroundTasks（不阻塞响应）；失败仅记 warn 日志
- request_id 在 middleware 已生成（T1.8），service 通过 `Request.state.request_id` 取

**验收**：
```
# tests/modules/agent/test_invoke.py
async def test_invoke_echo_non_stream(client, app_key, mock_echo_agent):
    r = await client.post(
        "/v1/agents/echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hello", "stream": False}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] and body["code"] == 200
    assert body["data"]["session_id"].startswith("sess_")
    assert "hello" in body["data"]["answer"]

async def test_invoke_list_messages_form(client, app_key):
    r = await client.post(
        "/v1/agents/echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": [
            {"role":"user", "content":"q1"},
            {"role":"assistant", "content":"a1"},
            {"role":"user", "content":"q2"},
        ], "stream": False}
    )
    # 验证 session 是新签发的、user msg "q2" 已落库、history 仅在内存
    ...

pytest chameleon-app/tests/modules/agent/ -v
```

---

### Task 3.4 - admin/call-logs + providers/status

**输入**：设计文档 S3.3 admin 段、S4.1 call_logs schema

**输出**：
- `modules/api_key/service.py` 加：`list_call_logs(filters, page, page_size) -> PageResult[CallLogItem]`
- `modules/api_key/api.py` 加：
  - `GET /v1/admin/call-logs?app_id=&agent_key=&since=&until=&success=&page=&page_size=`（四维过滤）
  - `GET /v1/admin/providers/status`（遍历 PROVIDERS，调每个 `healthcheck()`，返 `{name, ok, last_check_at}`）

**关键决策点**：
- 时间过滤用 ISO8601；service 层转 datetime
- providers/status 不缓存（直接每次 ping），v1 OK

**验收**：
```
curl "localhost:8000/v1/admin/call-logs?app_id=my-app&success=false" \
  -H "Authorization: Bearer chm_<admin>"
# 返回该 app 的失败调用列表

curl localhost:8000/v1/admin/providers/status \
  -H "Authorization: Bearer chm_<admin>"
# 返回 [{"name":"langgraph","ok":true},{"name":"dify","ok":true},...]
```

---

### Task 3.5 - Phase 3 集成验收（非流端到端） + commit

**输入**：T3.1-T3.4 全部产物

**输出**：
- 集成测试脚本 `tests/integration/test_e2e_non_stream.py`：
  1. CLI `chameleon init-admin` 落第一个 admin key
  2. admin key 发普通 app key
  3. 用 app key 调 echo agent（v1 echo 在 P6 写，此处先用 mock provider）
  4. session_id 自动签发；继续传 session_id，历史回放正确
  5. 用 admin key 查 call_logs，存在 2 条记录
- commit：`feat(modules): 完成业务模块非流路径（agent/conversation/api_key + admin）`

**验收**：`pytest tests/integration/test_e2e_non_stream.py -v` 通过。

---

# Phase 4：SSE 流式

**Goal**：把流式路径打通。客户端 `stream=true` 时拿到 SSE 字节流，事件类型完整，断流不污染数据库。

**Output**：`POST /v1/agents/{key}/invoke` 支持 SSE；端到端集成测试覆盖 delta/step/citation/done/error 各种 event；断流不写 assistant msg。

**估时**：2 天。

---

### Task 4.1 - SSE 序列化层

**输入**：设计文档 S3.5（流式响应）

**输出**：
- `chameleon-app/src/chameleon/app/modules/agent/stream.py`：
  - `serialize_sse(event: StreamEvent) -> bytes`：按 `event: <type>\ndata: <json>\n\n` 格式
  - `sse_response(generator: AsyncIterator[StreamEvent]) -> StreamingResponse`：包装 FastAPI StreamingResponse，`media_type="text/event-stream"`
  - 心跳：每 15s 发 `: ping\n\n` 注释行（防中间代理超时切流），用 `asyncio.wait_for` + 兜底 yield

**关键决策点**：
- `: ping` 是 SSE 注释行（客户端忽略），保活连接
- 单 event size 受 `inventory.stream_chunk_flush_ms()` 与 `max_event_size_kb` 约束（v1 不强切，长内容自然 yield）

**验收**：
```python
# tests/test_sse.py
def test_serialize_delta():
    ev = StreamEvent(type=StreamEventType.delta, data={"text": "hi"})
    assert serialize_sse(ev) == b'event: delta\ndata: {"text":"hi"}\n\n'

def test_serialize_done():
    ev = StreamEvent(type=StreamEventType.done, data={"answer":"hi","session_id":"s"})
    out = serialize_sse(ev).decode()
    assert out.startswith("event: done\n")
```

---

### Task 4.2 - service.invoke 流式分支 + 落库时机

**输入**：设计文档 S4.3 ⑥⑦（流式落库）、A3

**输出**：
- `modules/agent/service.py` 加 `async def stream_invoke(agent_key, request, current_app, request_id) -> AsyncIterator[StreamEvent]`：
  - 同非流的 ①②③④⑤
  - ⑥：`async for ev in provider.stream(ctx)`：
    - 透传所有 event 给上游
    - `delta` 累积 answer_buf
    - `step/citation/tool_call/tool_result` 累积到对应列表
    - `done` event 拿到完整 result
    - `error` event 设 `failed=True`，**跳过 ⑦**
  - ⑦：仅在未 failed 时 append assistant msg + touch + call_log；failed 时仅 call_log（success=False）
  - 异常（连接断、客户端取消）：捕获 `asyncio.CancelledError` → 仅 log warn + call_log → **不写 assistant**

- `api.py` 改：`POST /v1/agents/{key}/invoke` body.stream=true 时 return `sse_response(service.stream_invoke(...))`

**关键决策点**：
- A3：断流 / provider error / 客户端 cancel —— 三者一致处理：**不落 assistant msg**，user msg 已写在 ④ 之前
- 流式响应不能用 Result.fail 兜底（已 200 + 流式 header）；error 通过 `event: error` 推送，调用方按事件类型识别

**验收**：
```
# tests/test_invoke_stream.py
async def test_stream_all_events(client, app_key):
    async with client.stream(
        "POST", "/v1/agents/echo/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hi", "stream": True}
    ) as r:
        events = parse_sse(r.aiter_bytes())
        assert {"delta", "step", "done"} <= {e.event for e in events}

async def test_provider_error_no_assistant_msg(client, app_key, mock_failing_provider):
    # 验证 error event 出现，assistant msg 未落库
    ...
```

---

### Task 4.3 - 多轮流式 + 历史正确性集成测试

**输入**：T4.1, T4.2

**输出**：
- `tests/integration/test_e2e_stream.py`：
  - 流式第一轮：input=str，无 session_id → 拿到 session_id
  - 流式第二轮：input=str，带上 session_id → 验证 history 加载正确（agent 能"记得"前一轮）
  - 流式 list[Message] 形态 → 验证不消费 session 历史

**验收**：`pytest tests/integration/test_e2e_stream.py -v` 通过。

---

### Task 4.4 - Phase 4 commit

**输出**：commit：`feat(stream): 加入 SSE 流式路径与正确的落库时机`

---

# Phase 5：向量与知识库

**Goal**：把 RAG 链路打通：建 KB、ingest 文档（异步 task）、search、本地 agent 内 search_kb 入口。

**Output**：`/v1/knowledge/*`、`/v1/tasks/{id}` 全可用；`from chameleon.core.knowledge import search_kb` 可用。

**估时**：4.5 天。

---

### Task 5.1 - core/embedding 工厂

**输入**：设计文档 S5（model.json）、A9

**输出**：
- `chameleon-core/src/chameleon/core/embedding/`
  - `base.py` — `class EmbeddingClient(Protocol)`：`async def embed(texts: list[str]) -> list[list[float]]`，`dim: int`
  - `openai_compat.py` — `class OpenAICompatEmbedding`：用 `httpx` 调 `{base_url}/embeddings`，支持 OpenAI 协议
  - `factory.py` — `get_embedding_client(name: str | None = None) -> EmbeddingClient`：name=None 用 `inventory.case_embedding()`；按 model_settings 找 provider → 拿 baseurl + key → 实例化

**关键决策点**：
- A9：v1 只支持 OpenAI 协议；非兼容厂商以后再加
- 批量 embed 内部自动分 batch（每批 ≤ 64 条）
- 返回值固定 list[list[float]]，dim 一致

**验收**：
```python
# tests/test_embedding.py
@respx.mock
async def test_embed_batch():
    respx.post("...").mock(return_value=Response(200, json={...}))
    client = get_embedding_client()
    vecs = await client.embed(["hello", "world"])
    assert len(vecs) == 2 and len(vecs[0]) == client.dim
```

---

### Task 5.2 - core/vector（VectorStore 协议 + pgvector 实现）

**输入**：设计文档 S4.5、A13

**输出**：
- `chameleon-core/src/chameleon/core/vector/`
  - `base.py` — `class VectorStore(Protocol)`（按 S4.5）+ `ChunkPayload` + `ChunkHit` dataclass
  - `pgvector.py` — `class PgVectorStore`：
    - `upsert(kb_id, chunks)` — bulk insert（用 `Chunk` ORM）
    - `search(kb_id, query_vec, top_k, filter)` — `SELECT ... ORDER BY embedding <=> :vec LIMIT :k WHERE kb_id = :kb`，附带 cosine 距离作 score
    - `delete(kb_id, doc_id=None)` — `DELETE FROM chunks WHERE kb_id=:kb AND (:doc IS NULL OR doc_id=:doc)`
    - `healthcheck()` — `SELECT 1`
  - `chroma.py` — 占位（仅一个 NotImplementedError 实现，注释说明何时切回）
  - `factory.py` — `get_store(backend="pgvector") -> VectorStore`

**关键决策点**：
- 用 sqlalchemy 而非 raw SQL（除非性能瓶颈），保持一致性
- search 用 `<=> ` 操作符（cosine distance，pgvector 推荐 + HNSW 索引适配）
- score 转换：`score = 1 - distance`（cosine 距离 0-2 → 相似度 1 到 -1）；返回前过滤 `score > 0`（filter 选项可调阈值）

**验收**：
```python
async def test_pgvector_search(db_session, fixture_kb_with_chunks):
    kb_id, _ = fixture_kb_with_chunks
    store = PgVectorStore()
    hits = await store.search(kb_id, query_vec=[0.1]*1536, top_k=3)
    assert 1 <= len(hits) <= 3
    assert all(0 <= h.score <= 1 for h in hits)
```

---

### Task 5.3 - core/knowledge.py（in-process search_kb）

**输入**：设计文档 S4.4（双面入口）

**输出**：
- `chameleon-core/src/chameleon/core/knowledge.py`：
  - `async def search_kb(kb_key: str, query: str, top_k: int = 5, filter: dict | None = None) -> list[ChunkHit]`
    1. 取 KB 元信息（kb_key → KB row）
    2. embedding_client.embed([query]) → vec
    3. store.search(kb_id, vec, top_k, filter)
    4. 返回 hits
  - `async def get_kb_meta(kb_key: str) -> KbMeta | None`
  - 内部依赖：`db.AsyncSessionLocal`、`embedding.get_embedding_client`、`vector.get_store`

**关键决策点**：
- `search_kb` 用 `async with AsyncSessionLocal()` 自己起会话（不依赖 FastAPI request scope，agent 内可用）
- v1 默认参数：top_k 缺省取 `inventory.kb_default_top_k()`

**验收**：
```python
async def test_search_kb_e2e(fixture_kb):
    kb_key = fixture_kb
    hits = await search_kb(kb_key=kb_key, query="hello", top_k=3)
    assert isinstance(hits, list)
```

---

### Task 5.4 - modules/knowledge（CRUD + search）

**输入**：设计文档 S3.3 knowledge 段、S4.1 knowledge tables

**输出**：
- `chameleon-app/src/chameleon/app/modules/knowledge/`
  - `schemas.py` — `KbCreate`, `KbUpdate`, `KbItem`, `DocumentItem`, `IngestRequest`, `SearchRequest`, `SearchHit`
  - `service.py`：
    - `create_kb / update_kb / delete_kb / list_kbs / get_kb`
    - `list_documents / delete_document`
    - `search(kb_key, query, top_k) -> list[SearchHit]`（薄包装 `core.knowledge.search_kb`）
  - `api.py`：按 S3.3 knowledge 段全部 8 个端点
  - ingest 端点在 T5.6 完成

**关键决策点**：
- KB 维度强制 = 全局 `inventory.embedding_dim()`（v1 锁 1536），如声明不一致 → reject create
- delete_kb 软删 KB（不删 documents/chunks，等异步 worker 清理；v1 简化版**仅软删 KB 行**，物理 chunks 留底——加 admin 命令清扫）

**验收**：
```
curl -X POST localhost:8000/v1/knowledge \
  -H "Authorization: Bearer chm_<app>" \
  -d '{"kb_key":"sales-docs","name":"销售文档","embedding_model":"text-embedding-3-small"}'

curl -X POST localhost:8000/v1/knowledge/sales-docs/search \
  -d '{"query":"销售额","top_k":3}'
```

---

### Task 5.5 - modules/task

**输入**：设计文档 S4.6（异步 ingest 数据流）、S3.3 task 段

**输出**：
- `chameleon-app/src/chameleon/app/modules/task/`
  - `schemas.py` — `TaskItem`
  - `service.py`：`create_task / update_task / get_task`
  - `api.py`：`GET /v1/tasks/{id}`

**关键决策点**：
- 普通 app key 仅能看自己创建的 task（service 加 `app_id` filter）；admin 看全量
- task 不允许从 HTTP 取消（v1）；如需取消由 admin DB 直改

**验收**：
```
curl localhost:8000/v1/tasks/<id>
# 返回 {status, progress, message, ...}
```

---

### Task 5.6 - 异步 ingest worker

**输入**：设计文档 S4.6、A11（任务）

**输出**：
- `chameleon-app/src/chameleon/app/modules/knowledge/ingest.py`：
  - `async def run_ingest_task(task_id: int, document_id: int, kb_id: int)`：
    1. task.running
    2. 从 documents 取内容（按 source_type / source_uri 解析）
       - text：直接用 `meta["content"]`
       - url：httpx 拉取
       - file：从本地路径或 storage 读
    3. 切块（用 `inventory.kb_chunk_size()` + `kb_chunk_overlap()`，简单按字符切；未来切 tokenizer）
    4. 批量 embed
    5. PgVectorStore.upsert
    6. document.ready，task.success
    7. 失败：document.failed + task.failed + error JSONB
- `modules/knowledge/api.py` 加：`POST /v1/knowledge/{kb_key}/documents`：
  - service.create_document_pending() → 创建 doc + task → `background_tasks.add_task(run_ingest_task, ...)` → 返 Result.ok({task_id, document_id, status: "queued"})

**关键决策点**：
- v1 用 FastAPI `BackgroundTasks` 注入；不需要外部 worker
- 内存中 await embedding —— 大文档可能占内存几百 MB，v1 接受；未来切 Arq
- 文件 ingest v1 支持：text/plain、text/markdown（直接当 plain）；其它返 400 + "format not supported in v1"

**验收**：
```
# 创建 ingest
curl -X POST localhost:8000/v1/knowledge/sales-docs/documents \
  -H "Authorization: Bearer chm_<app>" \
  -d '{"title":"Q1 报告","source_type":"text","content":"今年Q1销售额..."}'
# → {data: {task_id, document_id, status:"queued"}}

# 轮询直到完成
curl localhost:8000/v1/tasks/<id>
# → status: success

# search 检索得到
curl -X POST localhost:8000/v1/knowledge/sales-docs/search \
  -d '{"query":"Q1 销售"}'
# → 含命中
```

---

### Task 5.7 - Phase 5 集成验收 + commit

**输出**：
- `tests/integration/test_e2e_knowledge.py`：建 KB → ingest 多文档 → 轮询 task → search → 验证 hits 合理
- commit：`feat(knowledge): 完成向量存储与知识库全链路（infra/vector + modules/knowledge + modules/task + ingest worker）`

---

# Phase 6：本地 echo agent + 端到端冒烟

**Goal**：以 echo agent 为范式样板把 LangGraph 本地 agent 完整跑通；对 DIFY / FastGPT 用 mock 演示外部 agent。

**Output**：echo agent 可调（非流 + 流式）；DIFY / FastGPT 各一个 mock 集成测试通过。

**估时**：2 天。

---

### Task 6.1 - chameleon-agents/echo 完整实现

**输入**：设计文档 S1.1 agents 段、S2.3 agent 注册约定

**输出**：
- `chameleon-agents/echo/pyproject.toml` — deps: `chameleon-core`, `chameleon-providers-base`, `langgraph`
- `src/chameleon/agents/echo/__init__.py`：
  ```python
  # 伪代码
  from .graph import build_graph
  AGENT_META = {
      "key": "echo",
      "description": "回声智能体，原样返回输入 + 假步骤 + 假引用，用于冒烟验证",
      "version": "0.1",
      "tags": ["builtin", "test"],
  }
  ```
- `src/chameleon/agents/echo/graph.py`：实现一个 LangGraph CompiledGraph，3 个节点：
  - `route` 节点：emit 一个 step event
  - `lookup` 节点：调 `chameleon.core.knowledge.search_kb`（如果 input 命中 "doc:" 关键字）emit citation
  - `respond` 节点：emit delta token 流回声 input

**关键决策点**：
- echo agent 即同时演示 step / citation / delta 三类 event 的范式样板
- 不真正调 LLM；用普通 Python str 操作模拟 token 流（用 `yield` 单字符 delta）

**验收**：
```
# 集成测试
async def test_echo_streaming():
    events = await call_invoke_stream("/v1/agents/echo/invoke", {"input": "你好"})
    assert any(e.type == "delta" for e in events)
    assert any(e.type == "step" for e in events)
    assert events[-1].type == "done"
    assert "你好" in events[-1].data["answer"]
```

---

### Task 6.2 - 配置一个 DIFY mock agent + 端到端冒烟

**输入**：T2.3 dify fixtures

**输出**：
- `tests/integration/conftest.py` 加 `mock_dify_server`（用 `respx` 或 `pytest-httpserver` 起 mock）
- `tests/integration/test_e2e_dify.py`：
  - 在测试 fixture 里临时写一个 `agents.yaml` 加 mock dify agent
  - 重启 app（fixture 级别）
  - 调 `/v1/agents/mock-dify-faq/invoke`
  - 验证返回 + provider_conv_id 双写正确（第二轮带 provider_conv_id）

**关键决策点**：
- mock server 返回 DIFY 真实 SSE 格式（用 fixture 文件）
- 测试用 monkeypatch 注入临时 endpoint

**验收**：`pytest tests/integration/test_e2e_dify.py -v` 通过。

---

### Task 6.3 - 配置一个 FastGPT mock agent + 端到端冒烟

**输入**：T2.4 fastgpt fixtures

**输出**：与 T6.2 同构，`tests/integration/test_e2e_fastgpt.py`

**验收**：通过。

---

### Task 6.4 - Phase 6 commit

**输出**：commit：`feat(agents): 加入 echo 本地 agent 范式 + DIFY/FastGPT 端到端冒烟`

---

# Phase 7：文档 + v1 验收

**Goal**：让任何人（包括未来的自己）打开仓库 5 分钟就能起来，且 v1 验收清单全过。

**Output**：README、操作指南、CLI 指南、扩展指南、acceptance-report.md。

**估时**：2 天。

---

### Task 7.1 - README.md（顶层）

**输入**：设计文档全文

**输出**：
- `README.md`：
  - 项目定位（一段）
  - 技术栈表
  - 5 分钟快速开始（clone → docker compose up pg → uv sync → 拷贝 example 配置 → alembic upgrade → init-admin → 第一个 curl）
  - 目录指引（每个子包一句话）
  - 链接到 docs/plans/ + docs/operations.md + docs/extension-guide.md + docs/cli.md

**验收**：拿干净环境跑一遍 README 的 quickstart，全程不报错。

---

### Task 7.2 - docs/operations.md

**输入**：设计文档 S5 + Phase 0 部署细节

**输出**：
- 部署：docker-compose、env 变量清单、卷挂载
- Alembic 操作：upgrade / downgrade / autogenerate 流程 + 红线（不改已发布 migration）
- 备份：PG dump + chunks 表向量大小估算
- 升级：从 v0.1 → v0.2 的标准动作

---

### Task 7.3 - docs/cli.md

**输出**：
- `chameleon` 所有命令清单（init-admin / db upgrade 等）
- 示例 + 输出截图（文本）

---

### Task 7.4 - docs/extension-guide.md

**输入**：设计文档 S6.1

**输出**：
- 加新本地 agent 的 step-by-step（含完整 pyproject.toml 模板 + __init__.py 模板）
- 加新外部 DIFY/FastGPT agent 的 yaml 模板
- 加新 provider 的 step-by-step（含 Provider 协议实现 checklist）
- 加新 vector store 的 step-by-step

---

### Task 7.5 - v1 验收清单跑一遍 + acceptance-report.md

**输入**：设计文档 S6.3 验收清单（功能/架构/规约三轴）

**输出**：
- `docs/plans/2026-05-20-chameleon-v1-acceptance-report.md`：
  - 功能轴 11 项逐条勾选 + 证据（命令 + 输出片段）
  - 架构轴 6 项逐条勾选
  - 规约轴 8 项逐条勾选（`ruff check`、`mypy`、grep `print(` / `logging.` 等）
- 失败项：列出未通过 + 决策（带病发布 vs 补丁回流）

**验收**：所有可勾选项目要么 ✅ 要么有明确决策。

---

### Task 7.6 - Phase 7 commit + 打 tag

**输出**：
- commit：`docs(v1): 完成 README / operations / cli / extension-guide / 验收报告`
- `git tag v0.1.0 -m "Chameleon v1 ready for personal deployment"`

---

## v1 全量 commit 节奏摘要

| Phase | Commit Message Prefix |
|---|---|
| P0 | `chore(scaffold):` |
| P1 | `feat(core):` |
| P2 | `feat(providers):` |
| P3 | `feat(modules):` |
| P4 | `feat(stream):` |
| P5 | `feat(knowledge):` |
| P6 | `feat(agents):` |
| P7 | `docs(v1):` |

每个 Phase 内每个 Task 也可独立 commit（颗粒度自选），但 Phase 结束必有一次集成 commit。

---

## 总工时粗估

| Phase | 工作日 |
|---|---|
| P0 脚手架 | 1.5 |
| P1 chameleon-core | 3.5 |
| P2 Provider 抽象 + 三 provider | 3.5 |
| P3 业务模块骨架（非流） | 3.5 |
| P4 SSE 流式 | 2.0 |
| P5 向量与知识库 | 4.5 |
| P6 echo agent + 端到端冒烟 | 2.0 |
| P7 文档 + 验收 | 2.0 |
| **合计** | **22.5 工作日 ≈ 4.5 周** |

按周末休息 + 偶尔被打断的个人节奏，**4–6 周达成 v1** 是合理预期。

---

## 后续（v1 之后，明确不在本计划内）

- ✗ OpenAI 兼容层
- ✗ Per-embedding-model 多 chunks 表
- ✗ 实时配额 / 限流
- ✗ Arq / Redis 队列
- ✗ Admin 前端 UI
- ✗ Prometheus / OTel
- ✗ AI 标题生成
- ✗ Webhook
- ✗ 多租户隔离

按需进入 v0.2 计划文档；本计划严格守住 v1 边界。

---

*实施计划结束。开始执行前，请先 review 本文档 + 设计文档；如发现冲突，以设计文档为准并回头修订本计划。*
