# Chameleon 设计文档

**日期**：2026-05-20
**作者**：links
**协作**：Claude Opus 4.7（1M context）
**状态**：设计稿，待 v1 实施

---

## 项目定位

**Chameleon** 是 links 个人的 AI 中枢应用，作为所有 AI 应用的统一入口。任何外部应用（不论语言、不论场景）通过 Chameleon 暴露的 HTTP API 即可获得 AI 能力，**无需在自己项目里再装 LangGraph/SDK**。

智能体来源支持三种（可扩展到第 N 种）：

1. **本地 LangGraph 手写编排**（Python in-process）
2. **DIFY 开发者 API**（HTTP 外调）
3. **FastGPT 开发者 API**（HTTP 外调）

**核心使命**：把 AI 智能体作为可积累、可复用的资产管理起来——"AI 飞轮"。

参考但不效仿的项目：
- `sage`（个人 LangGraph 项目，uv workspace 重型多包，吸收其架构 + 配置形态）
- `skcchatllm`（公司 FastGPT 网关，Java/Spring Boot 三层，仅作业务包装层参考，不效仿）

---

## 核心决策汇总

| # | 决策项 | 选择 | 锁定理由 |
|---|--------|------|----------|
| 1 | 对外 API 契约 | **统一自定义契约**（`POST /v1/agents/{key}/invoke`） | 底层 provider 对客户端透明，metadata 完整保留 |
| 2 | 会话与记忆归属 | **Chameleon 自己存 PG**，DIFY/FastGPT 能存的双写 | 取代 sage 的 MySQL 模式，对外只露 Chameleon session_id |
| 3 | 向量存储能力 | **核心内置 client + 顶层 `/v1/knowledge/*`** | 服务本地 agent + 外部应用两条路径，单一数据源 |
| 4 | Agent 注册机制 | **本地代码扫描 + 外部 YAML 声明**，DB 不存 agent 元数据 | 加 agent = 写代码或加 yaml 行，一个 commit 搞定 |
| 5 | 入口鉴权 | **按应用发独立 API key**（带 scope） | 多 app 接入需细粒度审计 + 隔离 |
| 6 | 项目骨架 | **uv workspace 多包**（学 sage） | 复杂 agent 必然超出单文件夹容量，预先准备多包结构 |
| 7 | Provider 抽象 | **`chameleon-providers/{name}` 每个 provider 独立子包** | 与 agents 对称，加新 provider 零接触老 provider |
| 8 | Input 形态 | **同时支持 `str` 和 `list[Message]`** | str→自动取历史，list→客户端自管历史 |
| 9 | Admin 鉴权 | **完整 admin scope 的 api_key 体系** | CLI bootstrap 第一个 admin key，之后全 HTTP |
| 10 | Embedding 维度 | **v1 全局单维 1536**（OpenAI text-embedding-3-small） | 单表简单；扩展点已留 |
| 11 | 异步 ingest | **v1 FastAPI BackgroundTasks** | 个人项目简化，未来切 Arq |
| 12 | 配置体系 | **pydantic-settings（.env）+ sage 风格 JSON Settings** | 强类型秘钥 + 灵活业务参数 |
| 13 | DB | **PostgreSQL + pgvector** | 取代 sage 的 MySQL；向量与业务表同事务边界 |

---

## S1. 项目骨架（uv workspace 多包）

### 1.1 目录树

```
Chameleon/                                    ← uv workspace 根
├── pyproject.toml                            ← [tool.uv.workspace]
│                                             members = ["chameleon-core",
│                                                        "chameleon-providers/*",
│                                                        "chameleon-agents/*",
│                                                        "chameleon-app"]
├── uv.lock
├── .env(.example)
├── config/
│   ├── chameleon.json
│   ├── baseurl.json
│   ├── model.json
│   ├── agents.yaml
│   ├── .env
│   └── example/
├── migrations/versions/                      ← Alembic（全局共享一个 PG）
├── docs/plans/                               ← 本设计文档
├── tests/                                    ← 跨包集成测试
│
├── chameleon-core/                           ★ 1 号包：基础设施 + AI infra + 共享 ORM
│   ├── pyproject.toml
│   └── src/chameleon/core/
│       ├── config/                           # Settings 类、env、inventory
│       │   ├── __init__.py
│       │   ├── constants.py
│       │   ├── base_settings.py
│       │   ├── env_settings.py
│       │   ├── json_settings.py
│       │   └── inventory.py
│       ├── logger.py                         # loguru
│       ├── exceptions.py                     # BusinessError 家族
│       ├── response.py                       # Result[T] / PageResult[T]
│       ├── db.py                             # SQLAlchemy async session
│       ├── auth.py                           # API Key middleware + Depends
│       ├── models/                           # ★ 共享 ORM（让 agent 可读）
│       │   ├── base.py                       # Base + 时间戳 + 雪花 ID
│       │   ├── api_key.py
│       │   ├── conversation.py               # conversations + messages
│       │   ├── knowledge.py                  # kb + documents + chunks
│       │   ├── call_log.py
│       │   └── task.py
│       ├── vector/                           # VectorStore 统一接口
│       │   ├── base.py
│       │   ├── pgvector.py
│       │   └── chroma.py
│       ├── llm/                              # LLM client 工厂
│       ├── embedding/                        # embedding 工厂
│       ├── http/                             # async HTTP client（DIFY/FastGPT 用）
│       ├── knowledge.py                      # in-process search_kb() 等
│       └── utils/                            # 纯函数（时间、雪花、json、hash）
│
├── chameleon-providers/                      ★ 分组目录（非包）
│   ├── base/                                 ← chameleon-providers-base
│   │   ├── pyproject.toml                    deps: chameleon-core
│   │   └── src/chameleon/providers/base/
│   │       ├── protocol.py                   # Provider 协议
│   │       ├── types.py                      # AgentDef / InvokeContext /
│   │       │                                 # InvokeResult / StreamEvent
│   │       ├── registry.py                   # 启动时构建 PROVIDERS + AGENTS
│   │       └── errors.py                     # ProviderError 家族
│   │
│   ├── langgraph/                            ← chameleon-provider-langgraph
│   │   ├── pyproject.toml                    deps: core, providers-base, langgraph
│   │   └── src/chameleon/providers/langgraph/
│   │       ├── __init__.py                   # export PROVIDER = LangGraphProvider()
│   │       ├── provider.py
│   │       ├── builder.py                    # graph 构建缓存
│   │       └── stream.py                     # langgraph events → StreamEvent
│   │
│   ├── dify/                                 ← chameleon-provider-dify
│   │   ├── pyproject.toml                    deps: core, providers-base
│   │   └── src/chameleon/providers/dify/
│   │       ├── __init__.py
│   │       ├── provider.py
│   │       ├── client.py                     # DIFY HTTP API 封装
│   │       └── stream.py                     # DIFY SSE → StreamEvent
│   │
│   └── fastgpt/                              ← chameleon-provider-fastgpt
│       ├── pyproject.toml                    deps: core, providers-base
│       └── src/chameleon/providers/fastgpt/
│           ├── __init__.py
│           ├── provider.py
│           ├── client.py                     # FastGPT HTTP API
│           └── stream.py
│
├── chameleon-agents/                         ★ 分组目录（非包），AI 飞轮
│   ├── echo/                                 ← v1 验证用，最简
│   │   ├── pyproject.toml
│   │   └── src/chameleon/agents/echo/
│   │       └── __init__.py
│   │
│   ├── sql_qa/                               ← 简单 agent 范式
│   │   ├── pyproject.toml
│   │   └── src/chameleon/agents/sql_qa/
│   │       ├── __init__.py                   # export build_graph + AGENT_META
│   │       ├── graph.py
│   │       ├── prompts.py
│   │       └── tools.py
│   │
│   └── data_qa_v2/                           ← 复杂 agent 范式（参考 sage）
│       ├── pyproject.toml
│       ├── tests/regression/
│       └── src/chameleon/agents/data_qa_v2/
│           ├── __init__.py
│           ├── agent.py
│           ├── deps_factory.py
│           ├── tools/
│           ├── prompts/
│           ├── nodes/
│           └── memory/
│
└── chameleon-app/                            ★ FastAPI 入口 + 业务模块
    ├── pyproject.toml                        deps: core + providers-base + 三个 provider 子包
    └── src/chameleon/app/
        ├── main.py                           # 挂 router、注册异常 handler、构建 registry
        ├── cli.py                            # chameleon init-admin、key ops、健康诊断
        └── modules/                          # 业务模块（按域切，同一包内）
            ├── agent/
            │   ├── api.py                    # POST /v1/agents/{key}/invoke
            │   ├── service.py                # 路由 → provider → 落 messages
            │   ├── schemas.py
            │   └── stream.py                 # SSE 序列化
            ├── conversation/
            │   ├── api.py
            │   ├── service.py
            │   └── schemas.py
            ├── knowledge/
            │   ├── api.py                    # /v1/knowledge/*
            │   ├── service.py
            │   ├── schemas.py
            │   └── ingest.py                 # 异步切块 + embedding worker
            ├── api_key/
            │   ├── api.py                    # /v1/admin/api-keys/*
            │   ├── service.py
            │   └── schemas.py
            └── task/
                ├── api.py                    # /v1/tasks/{id}
                ├── service.py
                └── schemas.py
```

### 1.2 命名空间与依赖图

所有子包共享 `chameleon.*` namespace（PEP 420）。import 永远写：
```python
from chameleon.providers.base.types import AgentDef
from chameleon.agents.sql_qa import build_graph
from chameleon.core.vector import get_store
```
物理在哪个子包，调用方无感。

**依赖图（铁律）**：

```
                   chameleon-core
                          ↑
              chameleon-providers-base
              ↑          ↑          ↑
        langgraph      dify     fastgpt    ← 横向：加新 provider 并列新增
              ↑          ↑          ↑
              └────── chameleon-app ──────┘

   chameleon-agents/<x>  →  chameleon-core（仅！）
```

- `chameleon-core` 不依赖任何包
- `chameleon-providers-base` 依赖 core
- 每个具体 provider（langgraph/dify/fastgpt）依赖 core + providers-base
- `chameleon-app` 依赖 core + providers-base + 所有具体 provider
- **每个 agent 子包只依赖 core**（这是"AI 资产可独立迁移"的物理保障）

### 1.3 项目骨架的关键设计意图

1. **业务模块（modules/）不独立成包**：它们共享 main.py 入口、共享 router 挂载、共享 Alembic，独立成包带来动态发现复杂度无收益。
2. **每个 agent 强制独立子包**（不论简单复杂）：简单的 5 行 pyproject.toml 无成本；升级路径单调（从来不用"从单文件搬到包"）。
3. **`chameleon-providers/` 和 `chameleon-agents/` 是分组目录，非包**：自身没 pyproject.toml，workspace `members` 用 glob `chameleon-providers/*` 自动收。
4. **`chameleon-providers-base` 是规范层**：定义 Provider 协议、AgentDef、StreamEvent。日后扩任何 provider 第一动作就是看它。
5. **共享 ORM 集中在 `chameleon-core/models/`**：让 agent 子包能合法读 knowledge_bases / chunks 等表。这是规约里"共用能力下沉"的体现。
6. **chameleon-app 不显式依赖每个 agent 包**：uv workspace 默认 editable 装所有 members，registry 启动时用 namespace 扫描自动发现。加 agent 不改 app 依赖列表。

---

## S2. Provider 抽象设计

### 2.1 四个核心数据类型（都在 `chameleon-providers-base`）

```
AgentDef          ← 一个 agent 在系统里的"身份证"
                    - key:            全局唯一 agent_key
                    - provider:       "langgraph" / "dify" / "fastgpt" / ...
                    - description / version / tags
                    - config:         dict（provider-specific）
                                      langgraph: {"module": "chameleon.agents.sql_qa",
                                                  "build_fn": "build_graph"}
                                      dify:      {"endpoint", "app_id",
                                                  "api_key_env", "mode": "chat|workflow"}
                                      fastgpt:   {"endpoint", "app_id", "api_key_env"}

InvokeContext     ← 每次调用的上下文包，service 层组装好喂给 provider
                    - agent_def:      AgentDef
                    - input:          str | list[Message]    ← 当前轮输入
                    - history:        list[Message]          ← Chameleon 自管的历史
                    - session_id:     str                    ← Chameleon 签发
                    - provider_conv_id: str | None           ← provider 原生会话 ID
                    - context_vars:   dict                   ← 客户端透传业务上下文
                    - app_id:         str                    ← 来自鉴权
                    - stream:         bool

StreamEvent       ← 统一流式事件（封闭枚举）
                    type ∈ {
                      delta         # 增量文本
                      step          # 中间步骤（含 thinking、节点完成等）
                      citation      # 命中的知识引用
                      tool_call     # 工具调用记录
                      tool_result   # 工具调用结果
                      metadata      # 流中的元数据（usage 等）
                      done          # 完成（data = 完整 InvokeResult）
                      error         # 流中错误（流不再继续）
                    }
                    data: dict（每种 type 有自己的 schema）

InvokeResult      ← 非流式返回的完整结果（也是流式 done 事件的 data 体）
                    - answer:         str
                    - session_id:     str
                    - request_id:     str
                    - steps:          list[StepRecord]
                    - citations:      list[Citation]
                    - tool_calls:     list[ToolCallRecord]
                    - usage:          {prompt_tokens, completion_tokens, total_tokens}
                    - raw:            dict | None    ← 仅 DEBUG 模式填充
```

**设计要点**：
- `InvokeContext` 把"会话归 Chameleon 管"的所有上下文打包送入 provider —— provider 是**准无状态**执行单元（除了缓存编译产物）。
- `StreamEvent.type` 是**封闭枚举**，封闭即承诺：新增类型要改 base + 所有 provider 同步。
- `InvokeResult` 即"流式 done 事件的 data"——非流和流式只差**协议层**，数据结构同源。

### 2.2 Provider 协议（最小接口）

```
abstract class Provider:
    name: str                                          # "langgraph" / "dify" / ...

    async def stream(ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """必须实现：统一流式契约"""

    async def invoke(ctx: InvokeContext) -> InvokeResult:
        """默认实现 = 把自己的 stream() 聚合；provider 有原生非流模式可 override"""

    async def healthcheck() -> bool:
        """启动时 ping，warn-only（不阻塞）"""
```

**只 `stream()` 必实现**。加 provider 实现成本几乎只剩"翻译你家事件流到 Chameleon StreamEvent"。

### 2.3 Registry 构建流程（启动时一次，运行时只读）

```
1) Provider 注册（扫 chameleon.providers.* namespace）:
   遍历 chameleon.providers.<name>.PROVIDER → dict[str, Provider]
   约定：每个 provider 子包 __init__.py 必须 export
         PROVIDER = <YourProvider>()

2) Agent 注册（双源合一）:
   a. 扫 chameleon.agents.* namespace
      每个 agent 子包 __init__.py 必须 export:
        AGENT_META = {"key": "sql-qa",
                      "description": "...",
                      "version": "0.1",
                      "tags": [...]}
        build_graph()                          ← LangGraphProvider 调用入口
      → 注册为 provider="langgraph" 的 AgentDef

   b. 读 config/agents.yaml（带 ${baseurl:x} / ${env:X} 占位符替换）
      每条 entry → 注册为对应 provider 的 AgentDef

3) 输出：两个全局只读 dict
   PROVIDERS:  dict[str, Provider]
   AGENTS:     dict[str, AgentDef]
```

**重复 key**：启动期 fail-fast，重复即报错退出。

### 2.4 三类 Provider 实现要点

```
LangGraphProvider (in-process)
  ├─ 内部维护 {agent_key: compiled_graph} 缓存
  ├─ 首次 invoke 时调 build_graph() → graph，后续直接使用
  ├─ state 构造时把 ctx.history 翻成 langgraph 的 messages
  └─ 监听 graph.astream_events，按节点 / token / tool_call 分别 yield StreamEvent

DifyProvider (HTTP 外调)
  ├─ 用 chameleon-core 的 http client（超时/重试/连接池）
  ├─ POST {endpoint}/chat-messages or /workflows/run
  ├─ 流式：解析 DIFY SSE (message/agent_thought/node_finished/...) → StreamEvent
  └─ 启用 provider_conv_id 时透传，双写到 conversations.provider_conv_id

FastGPTProvider (HTTP 外调)
  ├─ 用同款 http client
  ├─ POST {endpoint}/v1/chat/completions（OpenAI 兼容协议）
  ├─ 流式：解析 OpenAI delta + FastGPT responseData 扩展 → StreamEvent
  └─ chatId 同样双写
```

### 2.5 错误规范化

```
ProviderError (基类)
  ├─ ProviderConfigError        配置缺失 / api_key 未设
  ├─ ProviderUnreachableError   网络 / 超时 / DNS
  ├─ ProviderAuthError          provider 401/403
  ├─ ProviderRateLimitError     429
  ├─ ProviderInputError         provider 拒收输入（400）
  └─ ProviderInternalError      其它兜底
```

每个 provider 实现 catch 原生异常 → raise 对应 ProviderError。全局 exception handler 兜成统一 `Result.fail()`，**不泄漏 provider 原始堆栈给客户端**（日志里全留）。

### 2.6 服务层与 Provider 协作链（端到端）

```
POST /v1/agents/sql-qa/invoke
        ↓
modules/agent/api.py     (FastAPI 路由 + 鉴权 Depends + body 校验)
        ↓
modules/agent/service.invoke():
   1. AGENTS["sql-qa"] → AgentDef
   2. PROVIDERS["langgraph"] → Provider
   3. conversation_service.load_history(session_id)    ← 取历史
   4. 组装 InvokeContext
   5. if stream: provider.stream(ctx) → modules/agent/stream.py 序列化 SSE
      else:      result = await provider.invoke(ctx)
   6. conversation_service.append(user_msg + assistant_msg)
   7. api_key_service.record_call(app_id, agent_key, latency, success)
        ↓
统一 Result[InvokeResponse] 返回
```

- API 层只接收 + 校验 + 编排响应
- Service 层做编排 + 调 provider + 落 DB
- Provider 层只做翻译 + 转发（不接触 DB）
- 跨模块只调 service，绝不跨模块调 model

---

## S3. 对外 API 契约

### 3.1 路径与版本

- 业务接口：`/v1/...`
- 健康：`/healthz`、`/readyz`
- 破坏性变更走 `/v2/...`，共存渐进迁移

### 3.2 鉴权机制

**单一头**：`Authorization: Bearer <api_key>`

`api_keys` 表的 `scopes` 列驱动鉴权：

| scope | 含义 |
|---|---|
| `(空)` | 普通 app key，可调所有非 admin 接口 |
| `admin` | 管理员，可调 admin 接口 + 普通接口 |
| `agent:<key>` | 限定可调的 agent（v1 占位） |
| `kb:<key>` | 限定可访问的知识库（v1 占位） |

**Bootstrap**：CLI `chameleon init-admin --name <name>` 在空库时落第一个带 `admin` scope 的 key，明文回显一次。之后所有 admin 操作（发普通 key、撤 key、查日志）都走 HTTP + admin key，**无 master env token**。

**鉴权流程**（middleware）：
```
取 Authorization Bearer → sha256(key) → 查 api_keys（revoked_at IS NULL）
→ 设 request.state.app = {id, name, scopes}
→ 路由级 Depends 校验 scope（admin 接口要求 scopes ⊇ {"admin"}）
```

### 3.3 接口清单（前缀 `/v1`）

| 类别 | 路径 |
|---|---|
| **Agent 调用** | `POST /v1/agents/{key}/invoke` |
| | `GET /v1/agents` |
| | `GET /v1/agents/{key}` |
| **Conversation** | `GET /v1/conversations` |
| | `GET /v1/conversations/{session_id}` |
| | `GET /v1/conversations/{session_id}/messages` |
| | `POST /v1/conversations/{session_id}/delete` |
| **Knowledge** | `GET /v1/knowledge` |
| | `POST /v1/knowledge` |
| | `POST /v1/knowledge/{kb_key}/update` |
| | `POST /v1/knowledge/{kb_key}/delete` |
| | `POST /v1/knowledge/{kb_key}/documents` |
| | `GET /v1/knowledge/{kb_key}/documents` |
| | `POST /v1/knowledge/{kb_key}/documents/{id}/delete` |
| | `POST /v1/knowledge/{kb_key}/search` |
| **Task** | `GET /v1/tasks/{id}` |
| **Admin** | `POST /v1/admin/api-keys` |
| | `GET /v1/admin/api-keys` |
| | `POST /v1/admin/api-keys/{id}/revoke` |
| | `GET /v1/admin/call-logs`（支持 app/agent/时间窗/状态过滤） |
| | `GET /v1/admin/providers/status` |
| **健康** | `GET /healthz` |
| | `GET /readyz` |

### 3.4 统一响应封装（学 sage）

```python
class Result[T]:
    success: bool
    code:    int      # 200=成功，其它见错误码表
    message: str
    data:    T | None

class PageParams:
    page:      int = 1     # ge=1
    page_size: int = 10    # ge=1, le=100

class PageResult[T]:
    items:     list[T]
    total:     int
    page:      int
    page_size: int
```

所有列表接口的 `data` 类型 = `PageResult[XxxItem]`。

### 3.5 Agent Invoke 请求 / 响应

**Request**（`POST /v1/agents/{key}/invoke`）：

```json
{
  "input": "今天销售额",
  "session_id": "sess_xxx",
  "stream": false,
  "context": {"user_id": "u1", "tenant": "default"},
  "options": {"temperature": 0.5, "kb_keys": ["sales-2024"]}
}
```

`input` 支持两种形态：
- `str` → 服务端从 `session_id` 取历史拼接（无 session_id 则新建空会话）
- `list[Message]` → **不消费 session_id 历史**，客户端自管，最后一条作当前轮，前面作历史

**Non-stream Response**（`application/json`）：

```json
{
  "success": true, "code": 200, "message": "ok",
  "data": {
    "session_id": "sess_xxx",
    "request_id": "req_xxx",
    "answer": "今天销售额是 12,345 元",
    "steps": [
      {"name": "intent_route", "status": "success", "duration_ms": 23},
      {"name": "sql_runner",   "status": "success", "duration_ms": 156}
    ],
    "citations": [{"source": "doc_xxx", "score": 0.87, "snippet": "..."}],
    "tool_calls": [{"name": "execute_sql", "args": {...}, "result": {...}}],
    "usage": {"prompt_tokens": 320, "completion_tokens": 88, "total_tokens": 408}
  }
}
```

**Stream Response**（`text/event-stream`）：

```
event: delta
data: {"text":"今天"}

event: step
data: {"name":"sql_runner","status":"success","duration_ms":156}

event: citation
data: {"source":"doc_xxx","score":0.87,"snippet":"..."}

event: done
data: {"session_id":"sess_xxx","answer":"...","steps":[...],"usage":{...}}
```

流中错误：
```
event: error
data: {"code":60020,"message":"provider unreachable"}
```

`done.data` 与非流的 `data` **同源**——客户端两种模式可共用解析。

### 3.6 错误码（五位段位）

```
200       成功
-1        通用失败（兜底）

40001     ValidationError
40002     RequestSchemaError
40010     SessionIdInvalid
40020     InvalidStreamMode

40101     MissingApiKey
40102     InvalidApiKey
40103     ApiKeyRevoked

40301     AdminScopeRequired
40302     AgentNotInScope        (v1 占位)
40303     KbNotInScope            (v1 占位)

40401     AgentNotFound
40402     ConversationNotFound
40403     KnowledgeBaseNotFound
40404     DocumentNotFound
40405     TaskNotFound

42901     AppRateLimit            (v1 占位，先记录不限流)

50001     InternalError
50002     DBError
50003     RegistryError

60010     ProviderConfigError
60020     ProviderUnreachable
60030     ProviderAuthFailed
60040     ProviderRateLimit
60050     ProviderInputError
60090     ProviderInternalError
```

段位规则：前 3 位 ≈ HTTP semantic（4xx 客户端、5xx 服务端、6xx 给 provider 整段保留），后 2 位细分。**HTTP status 与业务 code 解耦**——HTTP 永远 200/4xx/5xx，业务码看 `data.code`。

**失败响应 message** 给客户端可读人话，**绝不带堆栈 / SQL / provider 原始报文**（这些都进日志）。

### 3.7 响应头

```
X-Request-Id: <req_xxx>             ← 与 data.request_id 一致
```

---

## S4. 数据模型 + 会话/记忆数据流 + 向量存储

### 4.1 PG Schema（核心表）

#### conversations
```
id                  BIGINT PK              （雪花）
session_id          VARCHAR(64) UK         （"sess_xxx" 对外暴露）
agent_key           VARCHAR(64) NOT NULL
provider            VARCHAR(32) NOT NULL   （冗余，便于过滤）
app_id              VARCHAR(64) NOT NULL
provider_conv_id    VARCHAR(255)           （DIFY/FastGPT 原生 ID，双写用）
title               VARCHAR(255)           （首轮自动生成，前 30 字截断）
meta                JSONB                  （context_vars 缓存）
last_message_at     TIMESTAMPTZ
created_at / updated_at / deleted_at TIMESTAMPTZ

INDEX (app_id, last_message_at DESC)
INDEX (agent_key, last_message_at DESC)
```

#### messages
```
id                  BIGINT PK
session_id          VARCHAR(64) NOT NULL
seq                 INT NOT NULL            （会话内顺序）
role                VARCHAR(16) NOT NULL    user/assistant/system/tool
content             TEXT
steps               JSONB                   （assistant：中间步骤）
citations           JSONB
tool_calls          JSONB
usage               JSONB
provider            VARCHAR(32)             （冗余，分析用）
created_at          TIMESTAMPTZ

INDEX (session_id, seq)
```

#### api_keys
```
id                  BIGINT PK
app_id              VARCHAR(64) UK          （slug "my-side-project"）
name                VARCHAR(128)
key_hash            VARCHAR(128) UK         （sha256(plaintext key)）
key_prefix          VARCHAR(16)             （首 8 字符回显）
scopes              JSONB                   （[] / ["admin"] / ["agent:x"]）
description         TEXT
created_by_id       BIGINT                  （FK 自指，谁发的）
last_used_at        TIMESTAMPTZ
created_at          TIMESTAMPTZ
revoked_at          TIMESTAMPTZ             （软撤）

INDEX (key_hash)
INDEX (app_id)
INDEX (revoked_at)
```

#### call_logs
```
id                  BIGINT PK
request_id          VARCHAR(64) UK
app_id              VARCHAR(64)
agent_key           VARCHAR(64)
session_id          VARCHAR(64)
stream              BOOLEAN
success             BOOLEAN
code                INT
error_message       TEXT
duration_ms         INT
prompt_tokens / completion_tokens / total_tokens   INT
created_at          TIMESTAMPTZ

INDEX (created_at DESC)
INDEX (app_id, created_at DESC)
INDEX (agent_key, created_at DESC)
INDEX (success, created_at DESC)
```

#### knowledge_bases
```
id, kb_key UK, name, description
embedding_model VARCHAR(64), embedding_dim INT
chunk_size INT, chunk_overlap INT
meta JSONB, created_at/updated_at/deleted_at
```

#### documents
```
id, kb_id FK, title, source_type (text/file/url), source_uri
mime_type, status (pending/chunking/embedding/ready/failed)
status_message TEXT, meta JSONB
created_at/updated_at/deleted_at

INDEX (kb_id, status)
```

#### chunks（pgvector）
```
id, doc_id FK, kb_id (冗余), seq, content TEXT, token_count INT
embedding VECTOR(1536)              ← v1 全局固定维度
meta JSONB

INDEX (kb_id)
INDEX (doc_id, seq)
INDEX USING hnsw (embedding vector_cosine_ops)
```

#### tasks
```
id, task_type (document_ingest / kb_reindex / ...)
ref_type, ref_id (引用对象)
status (queued/running/success/failed/cancelled)
progress INT(0-100), message TEXT, result JSONB, error JSONB
created_at, started_at, finished_at

INDEX (status, created_at)
INDEX (ref_type, ref_id)
```

### 4.2 v1 Embedding 维度妥协

`chunks.embedding VECTOR(N)` 表级固定。v1 锁：
- `config/model.json` 的 `cases.embedding = "text-embedding-3-small"`
- 全局维度 = 1536
- `knowledge_bases.embedding_model/dim` 字段记录但校验"与全局一致"
- 扩展点已留（未来按维度分表或动态建表）

### 4.3 会话/记忆数据流（端到端，单轮）

```
POST /v1/agents/sql-qa/invoke
{ "input": "...", "session_id": "sess_xxx" or null, "stream": true }
                   ↓
auth middleware → request.state.app = {app_id, scopes}
                   ↓
modules/agent/api.py        ← 校验 body、Depends 取 CurrentApp
                   ↓
modules/agent/service.invoke():

  ① 注册表查询      AGENTS["sql-qa"] → AgentDef(provider="langgraph", ...)

  ② 会话处理        if session_id 缺：
                       session_id = "sess_" + snowflake()
                       conv = conversation_service.create()
                     else：
                       conv = conversation_service.get(session_id)
                       校验 app_id 匹配、未软删

  ③ 历史装载        ★ S3 锁定规则
                     if input == list[Message]:
                         history = input[:-1]
                         current_input = input[-1].content
                     else:  # str
                         history = conversation_service.load_messages(
                                       session_id,
                                       limit=inventory.session_history_limit()
                                   )
                         current_input = input

  ④ 落库 user msg   conversation_service.append(
                       session_id, role=user, content=current_input
                   )
                   （先写，崩了也有痕迹）

  ⑤ 装 InvokeContext  ctx = InvokeContext(
                          agent_def, history, current_input,
                          session_id,
                          provider_conv_id=conv.provider_conv_id,
                          context_vars=body.context,
                          app_id, stream=body.stream
                      )

  ⑥ 调 provider    provider = PROVIDERS[agent_def.provider]
                    if stream:
                        async for ev in provider.stream(ctx):
                            modules/agent/stream.serialize_sse(ev) → yield 客户端
                            if ev.type == done: result = ev.data
                    else:
                        result = await provider.invoke(ctx)

  ⑦ 落库 assistant  conversation_service.append(
                       role=assistant, content=result.answer,
                       steps=result.steps, citations=result.citations,
                       tool_calls=result.tool_calls, usage=result.usage
                   )
                   ★ 流式断流情形下不写 assistant msg（视为本轮失败，下次重试）

  ⑧ 同步会话状态   conversation_service.touch(session_id, ...)
                     - last_message_at = now
                     - 首轮：title = 前 30 字截断（AI 生成开关默认关）
                     - provider_conv_id：provider 首次返回则记下（双写绑定）

  ⑨ 审计           api_key_service.record_call(
                       request_id, app_id, agent_key, session_id,
                       stream, success, code, duration_ms, usage
                   )
```

**双写策略落地点 = ⑤ 和 ⑧**：
- 调 provider 时传入 `provider_conv_id`，DIFY/FastGPT provider 内部：有就当 conversation_id 透传（原生会话状态延续）；没有就让 provider 新建并在响应里返回
- provider 首次回报新建的 conv_id 后 → service 写回 `conversations.provider_conv_id`
- LangGraph 永远 null

### 4.4 向量存储双面入口

**入口 A：HTTP 顶层**（外部应用用）
```
POST /v1/knowledge/{kb_key}/search    → modules/knowledge/service.search()
                                         ↓
                                       调 core/vector + core/embedding
```

**入口 B：In-process**（本地 agent RAG 用）
```python
# chameleon-agents/<x>/.../tools.py
from chameleon.core.knowledge import search_kb

async def kb_lookup_tool(query: str, kb_key: str) -> list[ChunkHit]:
    return await search_kb(kb_key=kb_key, query=query, top_k=5)
```

`chameleon.core.knowledge.search_kb()` 内部：
1. 取 KB 元信息（kb_key → KB row）
2. core/embedding 把 query 向量化
3. core/vector.search(kb_id=KB.id, vec, top_k) 查
4. 关联 chunks.meta 后返

**两个入口底层同一数据路径**。

### 4.5 VectorStore 抽象（`core/vector/base.py`）

```
class VectorStore(Protocol):
    async def upsert(kb_id: int, chunks: list[ChunkPayload]) -> None
    async def search(kb_id: int, query_vec: list[float], top_k: int,
                     filter: dict | None = None) -> list[ChunkHit]
    async def delete(kb_id: int, doc_id: int | None = None) -> None
    async def healthcheck() -> bool

ChunkPayload:  id, content, embedding, meta
ChunkHit:      id, content, score, meta, doc_id

实现：
  - PgVectorStore   ← v1 默认（与 PG 同实例，同事务边界）
  - ChromaStore     ← 占位，按需启用
```

### 4.6 异步 ingest 数据流

```
POST /v1/knowledge/{kb_key}/documents
        ↓
modules/knowledge/service.ingest():
  ① 创建 documents 行 (status=pending)
  ② 创建 tasks 行 (status=queued, ref_type=document, ref_id=doc.id)
  ③ FastAPI BackgroundTasks 投递（v1 简化，未来切 Arq）
  ④ 返 Result.ok({task_id, document_id, status: "queued"})

后台 worker：
  task.running → 切块（chunk_size+overlap） → embedding（批量）
  → 插 chunks 行 → document.ready → task.success

客户端轮询：GET /v1/tasks/{id} → Result.ok({status, progress, message, ...})
```

**v1 BackgroundTasks 限制**：进程级、无重试、容器重启即丢。够个人用。
**升级路径**：换 Arq（轻量、原生 async、Redis 后端）。

---

## S5. 配置体系

### 5.1 config/ 目录布局

```
config/
├── chameleon.json              ← 全局业务参数（开关、阈值、限制、超时）
├── baseurl.json                ← 外部 service URL 映射
├── model.json                  ← LLM / embedding 模型清单 + 默认 case
├── agents.yaml                 ← 外部 agent 注册（providers/base/registry 读）
├── .env                        ← 敏感配置（git ignore）
└── example/
    ├── chameleon.example.json
    ├── baseurl.example.json
    ├── model.example.json
    ├── agents.example.yaml
    └── .env.example
```

**git ignore**：`.env`、`chameleon.json`、`model.json`、`agents.yaml` 全 ignore（部署时填）。example 提交。

### 5.2 各文件职责

**`chameleon.json`**（业务参数）：

```json
{
  "log_level": "INFO",
  "session": {
    "history_limit": 20,
    "title_max_length": 30,
    "ai_title_generation": false
  },
  "knowledge": {
    "default_top_k": 5,
    "chunk_size": 800,
    "chunk_overlap": 100,
    "ingest_concurrency": 4
  },
  "stream": {
    "chunk_flush_ms": 50,
    "max_event_size_kb": 64
  },
  "provider_timeout_ms": {
    "dify": 60000,
    "fastgpt": 60000,
    "langgraph": 120000
  },
  "call_log": {
    "retention_days": null
  }
}
```

**`baseurl.json`**（外部 URL）：

```json
{
  "openai":          "https://api.openai.com/v1",
  "deepseek":        "https://api.deepseek.com/v1",
  "qwen":            "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "dify-default":    "https://dify.local/v1",
  "fastgpt-default": "https://fastgpt.local/api"
}
```

**`model.json`**（模型清单，★ 修补 sage 的安全漏洞——key 走 `key_env` 引用）：

```json
{
  "cases": {
    "llm":       "qwen-plus",
    "embedding": "text-embedding-3-small",
    "vision":    null
  },
  "providers": {
    "openai":   { "url_alias": "openai",   "key_env": "OPENAI_API_KEY" },
    "deepseek": { "url_alias": "deepseek", "key_env": "DEEPSEEK_API_KEY" },
    "qwen":     { "url_alias": "qwen",     "key_env": "QWEN_API_KEY" }
  },
  "models": {
    "llm": [
      { "name": "qwen-plus",     "provider": "qwen",     "temperature": 0.7, "max_tokens": 8000 },
      { "name": "deepseek-chat", "provider": "deepseek", "temperature": 0.5 }
    ],
    "embedding": [
      { "name": "text-embedding-3-small", "provider": "openai", "dim": 1536 }
    ]
  }
}
```

**`.env`**（敏感）：

```
DATABASE_URL=postgresql+asyncpg://chameleon:xxx@localhost:5432/chameleon
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO

OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx

DIFY_FAQ_KEY=app-xxxxxxxx
FASTGPT_ORDER_KEY=fastgpt-xxxxxxxx
```

**`agents.yaml`**（外部 agent 注册，支持 `${baseurl:x}` / `${env:X}` 占位）：

```yaml
- key: customer-faq
  provider: dify
  description: 客服 FAQ 机器人
  endpoint: ${baseurl:dify-default}
  app_id: ${env:DIFY_FAQ_APP_ID}
  api_key_env: DIFY_FAQ_KEY
  mode: chat

- key: order-analyst
  provider: fastgpt
  description: 订单分析助手
  endpoint: ${baseurl:fastgpt-default}
  app_id: ${env:FASTGPT_ORDER_APP}
  api_key_env: FASTGPT_ORDER_KEY
```

加载时统一替换占位符。

### 5.3 配置代码层（`chameleon-core/src/chameleon/core/config/`）

```
config/
├── __init__.py          # export 所有全局实例
├── constants.py         # 路径常量（CHAMELEON_ROOT / CONFIG_PATH，支持 env 覆盖）
├── base_settings.py     # 学 sage：BaseSettings 基类，点路径访问 + from_json/yaml
├── env_settings.py      # pydantic-settings：强类型 .env 绑定
├── json_settings.py     # ChameleonSettings / URLSettings / ModelSettings
└── inventory.py         # 具名 getter（学 sage inventory.py）
```

**两套机制并存**：

| 配置类型 | 机制 | 何时用 |
|---|---|---|
| 强类型敏感配置 | pydantic-settings 绑 `.env` | DB URL、API key 实值、log level |
| 弱类型业务参数 | 自封 BaseSettings 读 JSON | 业务阈值、模型清单、URL 映射 |

**inventory.py 示例**：

```python
def case_llm() -> str:
    return model_settings.get("cases.llm")

def llm_model_config(name: str) -> dict:
    for m in model_settings.get("models.llm"):
        if m["name"] == name: return m
    raise ConfigError(f"llm model not found: {name}")

def llm_provider_credential(provider: str) -> tuple[str, str]:
    cfg = model_settings.get(f"providers.{provider}")
    url = url_settings.get(cfg["url_alias"])
    key = os.environ.get(cfg["key_env"])
    if not key: raise ConfigError(f"env not set: {cfg['key_env']}")
    return url, key

def kb_default_top_k() -> int: return chameleon_settings.get("knowledge.default_top_k") or 5
def kb_chunk_size()    -> int: return chameleon_settings.get("knowledge.chunk_size") or 800
def session_history_limit() -> int: return chameleon_settings.get("session.history_limit") or 20
def stream_chunk_flush_ms() -> int: return chameleon_settings.get("stream.chunk_flush_ms") or 50
def database_url() -> str: return str(env_settings.DATABASE_URL)
```

**只给 getter，无 setter**——配置改通过编辑文件 + 重启，运行时不可变。

### 5.4 constants.py（路径，Docker 友好）

```python
_root_env = os.getenv("CHAMELEON_ROOT")
if _root_env:
    CHAMELEON_ROOT = Path(_root_env)
else:
    CHAMELEON_ROOT = Path(__file__).resolve().parents[5]   # → workspace 根

CONFIG_PATH = CHAMELEON_ROOT / "config"

_data_env = os.getenv("CHAMELEON_DATA")
DATA_ROOT = Path(_data_env) if _data_env else CHAMELEON_ROOT / "resources"

LOG_DIR = Path(os.getenv("CHAMELEON_LOG_DIR") or CHAMELEON_ROOT / "logs")
```

### 5.5 启动时加载顺序

```
1. constants.CHAMELEON_ROOT 确定
2. env_settings 加载（pydantic 解析 .env）
3. chameleon_settings / url_settings / model_settings 加载（读 JSON）
4. agents.yaml 由 registry.build_agent_registry() 读（带占位符替换）
5. providers/registry 扫 namespace + 合并 yaml → 全局 AGENTS / PROVIDERS
6. logger 启动（log_level 取自 inventory）
7. FastAPI app 装配
8. providers.healthcheck() 异步触发（warn-only）
```

---

## S6. 扩展指南 + YAGNI 切除 + v1 验收

### 6.1 扩展指南（"加新东西"的标准动作）

**加新本地 LangGraph agent**：
1. `mkdir chameleon-agents/<new_key>/`
2. 写 `pyproject.toml`（学 sql_qa，5 行模板）
3. 写 `src/chameleon/agents/<new_key>/__init__.py`：
   ```python
   from .graph import build_graph
   AGENT_META = {"key": "<new_key>", "description": "...", "version": "0.1"}
   ```
4. 写 `graph.py`（`build_graph()` 返回 LangGraph `CompiledGraph`）
5. `uv sync`
6. 重启 chameleon-app → registry 自动扫到、可调

**加新外部 DIFY/FastGPT agent**：
1. 在 `config/agents.yaml` 加一条 entry
2. 在 `.env` 加对应 `*_KEY`（如 `DIFY_NEWAPP_KEY=...`）
3. 重启 → 可调

**加全新 provider**（如 Coze、n8n）：
1. `mkdir chameleon-providers/<new_provider>/`
2. 写 `pyproject.toml` + 实现 Provider 协议（继承 `chameleon.providers.base.Provider`）
3. `__init__.py` export `PROVIDER = <YourProvider>()`
4. 重启 → agents.yaml 里就能用 `provider: <new_provider>`
5. **providers-base、其它 provider、所有 agent 代码零改动**

**加新 vector store**（如 Milvus、Qdrant）：
1. 在 `chameleon-core/src/chameleon/core/vector/` 新增 `<name>_store.py` 实现 VectorStore Protocol
2. 在 `chameleon.json` 切 `vector.backend = "<name>"`
3. 重启

### 6.2 v1 YAGNI 切除（明确不做）

- ❌ OpenAI-Compatible 适配层（用统一契约，未来出 1.0 再说）
- ❌ Per-embedding-model 多 chunks 表（v1 全局 1536 单维）
- ❌ 实时 message 向量化 / 会话语义检索（向量库只服务知识库）
- ❌ 流式断点续传（每次完整流，无 stream resumption）
- ❌ Webhook / Callback（同步 invoke + tasks 表轮询足够）
- ❌ 实时配额 / 限流（call_logs 留底 ≠ 实时拦截，后置补）
- ❌ 跨进程任务队列（v1 FastAPI BackgroundTasks）
- ❌ 多租户隔离（个人项目，app_id 仅审计）
- ❌ ProviderCapabilities 元数据
- ❌ Admin 前端 UI（CLI + HTTP 接口足够）
- ❌ Prometheus / OpenTelemetry（v1 用 loguru 文件日志 + call_logs 表）
- ❌ AI 标题生成（默认前 30 字截断，开关默认关）

### 6.3 v1 验收清单

**功能轴**：
- [ ] FastAPI app 可启动，`/healthz` / `/readyz` 通
- [ ] CLI `chameleon init-admin` 落第一个 admin key
- [ ] admin key 通过 `POST /v1/admin/api-keys` 发普通 app key
- [ ] 至少 1 个本地 LangGraph agent（`echo`）可调
- [ ] 至少 1 个外部 DIFY agent 接入并可调（占位 mock 可）
- [ ] 至少 1 个外部 FastGPT agent 接入并可调
- [ ] `POST /v1/agents/{key}/invoke` 非流 + SSE 两种模式都通
- [ ] `session_id` 自动签发 + 多轮历史回放正确
- [ ] `input: list[Message]` 模式不消费 session 历史，行为正确
- [ ] 创建 KB → ingest 文档（异步 task）→ search 三件套通
- [ ] 本地 agent 通过 `core.knowledge.search_kb()` 能拿到结果

**架构轴**：
- [ ] 依赖图：agent 子包仅依赖 core；providers 单向依赖 core + base
- [ ] 加新本地 agent 不动 chameleon-app、不动 providers
- [ ] 加新 provider 不动 base、不动其它 provider、不动 agent
- [ ] 所有接口返 Result[T] / PageResult[T]，无裸数据
- [ ] 全局异常 handler 接管，无业务 try/except 吞异常
- [ ] DB 全 PG，Alembic 受管，pgvector HNSW 索引就位

**规约轴**（python-codebase 红线）：
- [ ] API 层不写 SQL / 不直接调 Mapper
- [ ] Service 不返 ORM 给 API（schemas DTO 转）
- [ ] 类型注解齐全（所有函数签名）
- [ ] loguru `{}` 占位符，无字符串拼接日志
- [ ] 无 stdlib logging、无 `print` 调试遗留
- [ ] ruff 通过（含 isort）
- [ ] alembic 脚本带 `--rollback` / `<rollback>` 标注

---

## 附录 A：暴露面与扩展点速查

| 扩展点 | 入口 | 改动半径 |
|---|---|---|
| 新本地 agent | `chameleon-agents/<key>/` | 仅新子包 |
| 新外部 agent | `config/agents.yaml` + `.env` | 仅配置 |
| 新 provider | `chameleon-providers/<name>/` | 仅新子包 |
| 新 vector store | `core/vector/<name>_store.py` | 仅一个文件 |
| 新 LLM 厂商 | `baseurl.json` + `model.json` + `.env` | 仅配置 |
| 新业务模块 | `chameleon-app/.../modules/<name>/` + `main.py` 挂载 | app 单包内 |
| 新错误码 | `core/exceptions.py` 加常量 + handler 映射 | 单文件 |
| 新 StreamEvent 类型 | `providers/base/types.py` + 所有 provider 同步 | 横切 |

## 附录 B：v1 不解决但已留扩展点

| 待解项 | 锚点 |
|---|---|
| 多 embedding 维度共存 | 拆 `chunks_{dim}` 分表，或 KB 维度路由 |
| 跨进程任务队列 | `modules/task/service` 抽 worker 接口，切 Arq |
| OpenAI 兼容层 | 新增 `modules/openai_compat/` 路由前缀 `/v1/chat/completions` |
| 实时限流 | `core/auth.py` middleware 接 Redis token bucket |
| Webhook 异步回调 | `tasks` 表加 `webhook_url` 字段 + 任务完成后 POST |
| 会话语义检索 | message embedding worker → 独立 chunks 表 |

## 附录 C：与 sage / skcchatllm 的关系

| 项 | sage | skcchatllm | Chameleon |
|---|---|---|---|
| 语言 | Python | Java | Python |
| 框架 | FastAPI + LangGraph | Spring Boot + FastGPT 网关 | FastAPI + 三类 provider 统一 |
| 包结构 | uv workspace 多包 | 单模块按域切 | uv workspace 多包（学 sage） |
| Agent 形态 | LangGraph in-process | 全 FastGPT 远调 | 三类 + 可扩 |
| 会话存储 | MySQL（messages 自管） | 透传 FastGPT | PG 自管 + provider 双写 |
| 配置形态 | 多 JSON + 自封 Settings | application.yml | 多 JSON + pydantic-settings + .env |
| 鉴权 | 内部 | 公司单点 | per-app API key + admin scope |
| 向量存储 | Chroma + 内部 client | 无 | pgvector + 顶层 API + in-process |

**Chameleon 是 sage 形态 + skcchatllm 统一入口理念 + 个人飞轮诉求的合成体**。

---

*设计稿结束。下一步：交付 writing-plans skill 产出 v1 实施计划。*
