# 扩展指南

Chameleon 后端是 **10 个 uv-workspace 包**、import-linter 强制单向分层：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

扩展时几乎都只动**最外层**——加 agent 动 `chameleon-agents/`、加 provider 动 `chameleon-providers/<name>/`、加业务模块动 `chameleon-api/` 或 `chameleon-system/`，核心层基本不碰。

加东西的标准动作都很短——下面是 step-by-step。

---

## 1. 加一个本地 agent（agentkit `@agent` 范式）

**场景**：你要写一个新智能体，让它走 Chameleon 统一入口对外。

**总耗时**：~10-30 分钟（看业务逻辑复杂度）

★ 本地 agent 用 **`chameleon-agentkit` SDK** 书写：一个 `@agent` 装饰的 async 函数，从 `ctx`（`AgentRun`）隐式拿模型 / 知识库 / trace，框架完全解耦——不强制依赖 LLM / LangChain / LangGraph。

最小完整书写面：

```python
from chameleon.agentkit import AgentRun, agent


@agent(
    key="example-echo",                          # ★ 唯一 agent_key
    name="Echo（极简）",
    description="最小 @agent 范式：纯函数回声",
    tags=["example", "minimal"],
)
async def handle(ctx: AgentRun):
    yield f"echo: {ctx.query}"
```

声明「要模型」「要知识库」「要运营可调配置」时，往装饰器里加槽即可，运行时从 `ctx` 取：

```python
from chameleon.agentkit import AgentRun, ModelSlot, Opt, agent


@agent(
    key="example-rag-qa",
    name="RAG 问答",
    description="检索关联知识库 + 模型作答（自动引用）",
    tags=["example", "rag", "kb"],
    models=[ModelSlot("chat", "问答模型")],   # 具名模型槽；页面"关联模型"绑已配置模型
    kb=True,                                  # 页面"关联 KB"配的库被 ctx.kb.search 自动检索
)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=5)   # 未关联 KB → 返空，退化为直接作答
    async for delta in ctx.stream(slot="chat", context=docs or None, user=ctx.query):
        yield delta                          # ctx.stream 自动 trace + 命中自动发 citation
```

`ctx`（`AgentRun`）提供的核心方法：

| 方法 | 用途 |
|---|---|
| `ctx.query` / `ctx.config` | 本次输入 / 运营在页面调的配置（来自 `config=[Opt(...)]`） |
| `ctx.kb.search(query, top_k=...)` | 检索关联知识库；命中自动发 citation 事件 |
| `ctx.complete(slot=..., system=..., user=...)` | 非流式一次性补全（某模型槽） |
| `ctx.stream(slot=..., context=..., user=...)` | 流式补全，yield 文本增量 |
| `ctx.llm(slot=...)` / `ctx.kb.search(kbs=[...])` | 复杂 agent 在代码里直接点名模型 / KB，不依赖前端绑定 |

### Step 1 - 建子包目录

```bash
mkdir -p chameleon-agents/my_agent/src/chameleon/agents/my_agent
mkdir -p chameleon-agents/my_agent/tests
```

### Step 2 - 写 `pyproject.toml`

`chameleon-agents/my_agent/pyproject.toml`：

```toml
[project]
name = "chameleon-agent-my-agent"
version = "0.1.0"
description = "我的新 agent"
requires-python = ">=3.12"
dependencies = ["chameleon-agentkit"]

[tool.uv.sources]
chameleon-agentkit = { workspace = true }

# 推荐的注册方式：声明 entry-point，命名空间内外都能被发现
[project.entry-points."chameleon.agents"]
my-agent = "chameleon.agents.my_agent"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chameleon"]
```

### Step 3 - 写 `agent.py`（`@agent` 函数）

`chameleon-agents/my_agent/src/chameleon/agents/my_agent/agent.py`：

```python
from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent


@agent(
    key="my-agent",                       # ★ 唯一 agent_key（对外标识）
    name="我的智能体",
    description="干嘛用的一句话",
    tags=["domain-x"],
    models=[ModelSlot("chat", "对话模型")],
)
async def handle(ctx: AgentRun):
    async for delta in ctx.stream(slot="chat", user=ctx.query):
        yield delta
```

**约定**：
- 模块顶层有一个 `@agent` 装饰的 async 函数
- 装饰器 `key` 即对外 `agent_key`
- 函数 `yield` 文本增量 / `StreamEvent`

### Step 4 - export 函数

`chameleon-agents/my_agent/src/chameleon/agents/my_agent/__init__.py`：

```python
from chameleon.agents.my_agent.agent import handle

__all__ = ["handle"]
```

参考完整实现：
- 最小范式（零模型 / KB / 配置）：`chameleon-agents/examples/echo/`
- RAG 问答（模型槽 + KB）：`chameleon-agents/examples/rag_qa/`
- 多模型槽 + 运营配置：`chameleon-agents/examples/triage/`
- 真实业务（通用聊天）：`chameleon-agents/qwen_chat/`

> 有状态 / 多节点的复杂编排可改用 `BaseAgent` 子类（`from chameleon.agentkit import BaseAgent, AgentMetadata`，复写 `astream()` / `build_graph()` / `build_runnable()`，由 langgraph_bridge 桥接事件流）。`@agent` 函数覆盖绝大多数场景。

### Step 5 - RAG（声明 `kb=True` 即可）

```python
@agent(key="my-agent", name="...", kb=True, models=[ModelSlot("chat")])
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=5, min_score=0.3)
    async for delta in ctx.stream(slot="chat", context=docs or None, user=ctx.query):
        yield delta
```

`ctx.kb.search` 命中的片段会被自动 emit 为 citation event——作者不手写 citation，不直接 import 知识库 ORM。

### Step 6 - 装 + 重启

```bash
uv sync --all-packages           # 装新子包
uv run uvicorn chameleon.app.main:app --reload
```

启动日志的 Registry 摘要里应出现你的 agent：

```
─── Chameleon Registry ───
Loaded N agents:
  [local    ] my-agent                 (built-in)
```

### Step 7 - 调（`/v1/invoke` 唯一扁平入口）

agent 不暴露公开的 `/v1/agents/{key}/invoke`；对外只有一个 Dify 风扁平入口 `POST /v1/invoke`——**key 即应用身份**：

```bash
# app 作用域 key（chm_*）：key 已隐含目标 agent，不必传 agent_key
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input":"hi","stream":true}'
```

如果用的是全局作用域 key，则 body 里显式带 `agent_key`：

```bash
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $GLOBAL_KEY" \
  -d '{"input":"hi","agent_key":"my-agent","stream":true}'
```

`GET /v1/info` 返回当前 key 绑定的应用信息。应用列表 / 详情 / 启停 / 模型 · KB 绑定走 `/v1/admin/agents/*`（JWT 鉴权）。

### 业务 agent vs 示例 agent 怎么分

- 业务 agent（你真正用的）→ 放 `chameleon-agents/<key>/` 根目录
- 示例 / 范式样板（教学性质）→ 放 `chameleon-agents/examples/<key>/`

两者技术上完全一样，只是组织清晰度的约定。entry-points + `chameleon.agents.*` namespace 两层都发现得到。

### 依赖约束（铁律）

```
chameleon-agents/<x>  →  chameleon-agentkit    （仅！）
```

**agent 子包只能依赖 chameleon-agentkit**。这保证你的 AI 资产可独立迁移。
模型 / KB / trace 都从 `ctx` 隐式拿，不下穿到持久层或厂商实现包。

---

## 2. 加一个外部 DIFY agent

**场景**：你在 DIFY 平台编排好了一个 agent，想让 Chameleon 接入。

**总耗时**：~5 分钟（纯配置）

> DIFY agent 怎么被调用 / SSE 怎么翻译 / 错误怎么映射 → 见 [providers.md](providers.md) 的 "DifyProvider" 节

外部 agent（DIFY / FastGPT 等 HTTP 外调 provider）两种登记途径：在管理后台 `/v1/admin/agents/*` 录入，或在 `config/agents.yaml` 声明（本地 agent 由 namespace 自动发现，无需在此声明）。yaml 方式：

### Step 1 - 在 `config/agents.yaml` 加条目

```yaml
- key: customer-faq                  # ← 对外 agent_key
  provider: dify
  description: 客服 FAQ 机器人
  endpoint: ${baseurl:dify-default}  # 或 http://dify.yourcompany.com/v1
  app_id: ${env:DIFY_FAQ_APP_ID}     # DIFY 应用 ID（可选，纯记录用）
  api_key_env: DIFY_FAQ_KEY          # api key 从该 env 取
  mode: chat                         # chat | workflow
```

`mode` 字段：
- `chat` —— DIFY chat-messages 接口（多轮对话）
- `workflow` —— DIFY workflows/run（工作流编排）

占位符：`${baseurl:KEY}` 引用 `config/baseurl.json` 里的值，`${env:NAME}` 引用 `.env` 里的值。

### Step 2 - 在 `config/.env` 加 key

```env
DIFY_FAQ_KEY=app-xxxxxxxxxxxxxx
DIFY_FAQ_APP_ID=abcdef-1234       # 仅当你的 yaml 引用 ${env:DIFY_FAQ_APP_ID}
```

### Step 3 - 重启

```bash
uvicorn chameleon.app.main:app
```

启动日志的 Registry 摘要里应出现：

```
  [dify     ] customer-faq             (from agents.yaml)
```

### Step 4 - 调（与本地 agent 用法一致）

```bash
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input":"如何退货","stream":true}'
```

DIFY 的 `conversation_id` 由 provider 适配层与 Chameleon **Session** 双向绑定——下次带 `session_id` 调用时透传给 DIFY，DIFY 端会话状态延续。

---

## 3. 加一个外部 FastGPT agent

形态与 DIFY 完全对称。原理见 [providers.md](providers.md) 的 "FastGPTProvider" 节。

```yaml
- key: order-analyst
  provider: fastgpt
  description: 订单分析助手
  endpoint: ${baseurl:fastgpt-default}
  api_key_env: FASTGPT_ORDER_KEY
```

```env
FASTGPT_ORDER_KEY=fastgpt-xxxxxxx
```

FastGPT 的 `chatId` 同样与 Session 双向绑定。

---

## 4. 加一类全新 provider（如 Coze、n8n、自研编排）

provider 是独立子包：`chameleon-providers/<name>/src/chameleon/providers/<name>/`（参考内置的 `base` / `local` / `dify` / `fastgpt` / `graph`）。实现 `chameleon.providers.base.protocol` 里的 Provider 协议、注册到 registry 即可。

整章 step-by-step 已搬到 [providers.md](providers.md) 的 "如何加一个新 Provider" 节。

该文档还讲了 Provider 抽象层的整体原理 / 调用链 / 内置 provider 的内部实现，加新 provider 前建议先读一遍。

---

## 5. 加一个 vector store（如 Milvus、Qdrant、Chroma）

**场景**：默认 pgvector；你想切到 Milvus 之类的专业向量数据库。

VectorStore **协议**在 `chameleon-core`（纯 pydantic + Protocol），**实现 + 工厂**在 `chameleon-integrations`。已内置 `pgvector` / `chroma` 两个后端，加新后端照葫芦画瓢。

### Step 1 - 实现 VectorStore Protocol

`chameleon-integrations/src/chameleon/integrations/vector/milvus.py`：

```python
from chameleon.core.vector.base import ChunkHit, ChunkPayload, VectorStore


class MilvusStore(VectorStore):
    backend = "milvus"

    async def upsert(self, *, kb_id, doc_id, chunks: list[ChunkPayload]) -> None:
        # 调 milvus client
        ...

    async def search(self, *, kb_id, query_vec, top_k=5, min_score=0.0) -> list[ChunkHit]:
        ...

    async def delete(self, *, kb_id, doc_id=None) -> int:
        ...

    async def healthcheck(self) -> bool:
        ...
```

### Step 2 - factory 注册

`chameleon-integrations/src/chameleon/integrations/vector/factory.py` 的 `get_store()` 加分支：

```python
from chameleon.integrations.vector.milvus import MilvusStore

# ... 在 get_store() 内：
elif backend == "milvus":
    _STORE = MilvusStore()
```

### Step 3 - 配置切换

在 `config/chameleon.json` 里加：

```json
{
  "vector": {
    "backend": "milvus"
  }
}
```

工厂的 `_resolve_backend()` 留了 config 出口（默认 `pgvector`）；按需在 `chameleon.core.config.inventory` 暴露 `vector_backend()` getter 让它读到上面的配置。

### Step 4 - 重启

向量存储是单例，启动时实例化一次。

---

## 6. 加一种 LLM provider（embedding / chat）

默认 OpenAI 兼容协议（OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 同走）。

加新 OpenAI 兼容厂商**只需配置**：

`config/baseurl.json`：

```json
{
  "openai": "https://api.openai.com/v1",
  "moonshot": "https://api.moonshot.cn/v1"
}
```

`config/model.json`：

```json
{
  "providers": {
    "moonshot": { "url_alias": "moonshot", "key_env": "MOONSHOT_API_KEY" }
  },
  "models": {
    "embedding": [
      { "name": "moonshot-v1-embedding-2", "provider": "moonshot", "dim": 1536 }
    ]
  }
}
```

`config/.env`：

```env
MOONSHOT_API_KEY=ms-xxx
```

完事——不需要写代码。

**非 OpenAI 兼容协议的厂商**：
- embedding：写一个客户端实现（参考 `chameleon-core/src/chameleon/core/embedding/openai_compat.py`），在 `embedding/factory.py` 加分支。
- chat / LLM：实现接进 `chameleon-integrations/src/chameleon/integrations/llms/`（`base.py` 协议 + `factory.py` 工厂）。

---

## 7. 加一个业务模块（如 admin 面板、外部 webhook）

业务模块按"对外 / 对内"分两个包：

- **对外能力**（业务方调，前缀通常 `/v1/<resource>`）→ 放 `chameleon-api/src/chameleon/api/<name>/`
- **内部管理**（前端 admin 面板调，前缀 `/v1/admin/*`）→ 放 `chameleon-system/src/chameleon/system/<name>/`

### Step 1 - 建模块目录

```bash
# 对外能力示例
mkdir -p chameleon-api/src/chameleon/api/my_module
# 或：内部管理示例
mkdir -p chameleon-system/src/chameleon/system/my_module
```

### Step 2 - 标准文件

```
my_module/
├── __init__.py        # export router
├── schemas.py         # Pydantic DTO
├── service.py         # 业务逻辑（所有 SQL 在这层）
└── api.py             # FastAPI router
```

参考已有模块的范式：
- 对外：`chameleon-api/.../sessions/`、`chameleon-api/.../knowledge/`
- 对内：`chameleon-system/.../api_key/`、`chameleon-system/.../admin/`

### Step 3 - 挂到 main.py

router 在 `chameleon-app` 的 `_mount_routers()` 里集中挂载——加你的 import + `include_router`：

```python
# chameleon-app/src/chameleon/app/main.py
from chameleon.api.my_module import my_module_router   # 或 chameleon.system.my_module

def _mount_routers(app: FastAPI) -> None:
    ...
    app.include_router(my_module_router)
```

### 规约红线（必守）

来自 `~/.claude/rules/python-codebase.md`：

- ❌ API 层写 SQL / 业务循环
- ❌ Service 返 ORM 给 API（必须转 schemas DTO）
- ❌ 不包统一 `Result[T]` 直接返裸数据
- ❌ try/except 在 API 层吃异常（交给全局 handler）
- ✅ 所有 `BusinessError` 子类 raise 出去，全局 handler 接管
- ✅ loguru `{}` 占位符，禁止字符串拼接日志
- ✅ 类型注解齐全

---

## 8. 加一个 graph 工作流节点

**场景**：你要给可视化工作流引擎加一个新节点类型（默认已内置 LLM / KB / Tool / HTTP / Code 沙箱 / Template / 意图分类 / 聚合 / Answer / If-Else / Iteration / Parallel / AgentDebate / HumanInput）。

节点在 `chameleon-engine` 的 graph 引擎里。

### Step 1 - 写 Node 子类

`chameleon-engine/src/chameleon/engine/graph/nodes/my_node.py`，继承 `chameleon.engine.graph.node_base.Node`，声明 `type` 类属性 + 实现执行逻辑。

### Step 2 - 注册

文件末尾调装饰器：

```python
from chameleon.engine.graph.registry import register_node_type

register_node_type(MyNode)
```

`Orchestrator` 通过 `default_factory` 按 `NodeSpec.type` 查 class 实例化。**同一 `type` 不能重复注册不同 class**（启动期失败优于运行时神秘 bug）。

---

## 9. 加一个工具（graph ToolNode / LLM function calling 共用）

工具协议在 `chameleon-core/src/chameleon/core/tools/base.py`（`Tool` 抽象类），内置实现在 `chameleon-integrations/.../tools/builtins/`，全局 registry 在 `chameleon-integrations/.../tools/registry.py`。

### Step 1 - 写 Tool 子类

继承 `chameleon.core.tools.base.Tool`，声明 `tool_key` / `description` / `parameters_schema`（JSON Schema dict），实现 `async run(args, ctx)` 返 JSON-serializable 结果。

**红线**：Tool 不能持 db session（要数据走 service 依赖注入）、不直接 import 业务模块 service（避免反向依赖）、重型 / 不安全的 tool（SQL / Code）默认 disabled 由 admin 显式启。

### Step 2 - 注册

在 `builtins/<tool>.py` 末尾：

```python
from chameleon.integrations.tools.registry import register_tool

register_tool(MyTool)
```

业务侧 / graph ToolNode 通过 `get_tool_class(tool_key)` 取用。

---

## 10. 加新错误码

`chameleon-core/src/chameleon/core/api/exceptions.py` 加 enum 成员：

```python
class ResultCode(IntEnum):
    ...
    KbNotFound = 40450    # 新加；段位决定 HTTP status，见下
```

加对应 message：

```python
_CODE_MESSAGES = {
    ...
    ResultCode.KbNotFound: "知识库不存在",
}
```

派生 BusinessError 子类（可选）：

```python
class KbNotFoundError(BusinessError):
    code = ResultCode.KbNotFound
```

HTTP status 推断：`code_to_http_status` 按 `code // 100` 取段映射——`404xx → 404`、`400xx → 400`、`429xx → 429`、`5xxxx → 500`、`6xxxx → 502`。所以新错误码要让前三位落在 `400/401/403/404/409/422/429` 之一（如 `40450 // 100 = 404`）。

---

## 快查表

| 扩展点 | 入口 | 改动半径 |
|---|---|---|
| 新本地 agent | `chameleon-agents/<key>/`（`@agent` + agentkit） | 仅新子包 |
| 新外部 agent | `/v1/admin/agents/*` 或 `config/agents.yaml` + `.env` | 仅配置 |
| 新 provider | `chameleon-providers/<name>/` | 仅新子包 |
| 新 vector store | `integrations/.../vector/<name>.py` + factory | 单文件 |
| 新 LLM 厂商（兼容） | `baseurl.json` + `model.json` + `.env` | 仅配置 |
| 新业务模块 | `chameleon-api/.../<name>/` 或 `chameleon-system/.../<name>/` + main.py 挂载 | 按"对外/对内"选包 |
| 新 graph 节点 | `engine/.../graph/nodes/<name>.py` + `register_node_type` | 单文件 |
| 新工具 | `integrations/.../tools/builtins/<name>.py` + `register_tool` | 单文件 |
| 新错误码 | `core/api/exceptions.py` 加 enum | 单文件 |
| 新 StreamEvent 类型 | `providers/base/types.py`（`StreamEventType` 枚举）+ 各 provider 同步 | 横切 |
