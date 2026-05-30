# Chameleon 入门指南（使用者视角）

> 这份文档不讲怎么造 Chameleon，讲**你要用它做什么**。

---

## 一、Chameleon 是干嘛的

Chameleon = 开源 **LLMOps 一站式平台**：多源 AI 聚合 + 工作流编排 + RAG 知识库 + Trace/Eval 可观测 + 多 agent 协同 + 可嵌入 SDK。

```
你的某个应用（Web / 脚本 / Slack 机器人 / 移动 App）
        ↓ HTTP 调用
   ┌─────────────────┐
   │   Chameleon     │   ← 你部署的这个项目（统一 AI 服务面）
   │   POST /v1/invoke│
   └────┬────────────┘
        ↓ 内部分发（provider 抽象）
   ┌────┴─────┬─────────┬─────────┬─────────┐
   ↓          ↓         ↓         ↓         ↓
 本地        graph      DIFY      FastGPT    ...
 (进程内)    (工作流)    HTTP      HTTP       将来
```

**核心承诺**：你的应用只学**一个**调用方式（`POST /v1/invoke`），背后的智能体来源（本地进程内写的 / graph 工作流编排的 / DIFY 编排的 / FastGPT 编排的）随便换，**消费者代码不动**。

**对 agent 作者的承诺**：本地 agent SDK（`chameleon-agentkit`）**不锁死编排库**——你可以用：
- 纯 Python async 函数（最自由，`@agent` 装饰一下就行，可接任何 LLM SDK）
- LangChain Runnable / LCEL（链式简单调用）
- LangGraph CompiledGraph（复杂多节点，走 `BaseAgent`）
- 三种混合

所有范式产出的事件流统一为 Chameleon `StreamEvent`，对客户端完全透明。

---

## 二、后端是怎么分层的（10 个 uv-workspace 包）

后端是一个 uv workspace，拆成 10 个包，依赖方向**严格单向**（由 import-linter 强制护栏，2 个契约常驻 GREEN）：

```
core ← data ← integrations ← engine ← (providers / api / system / app / agents / agentkit)
```

| 包 | 职责 | 关键约束 |
|---|---|---|
| **chameleon-core** | 纯协议 + 数据结构 + `observe` 切面（ContextVar / sink 协议）+ 组件门面（`components.llm/embedding/...`） | 面向协议，业务代码统一从这里取组件 |
| **chameleon-data** | ORM 模型（SQLAlchemy 2.0 async）+ infra（db / redis / object_store / jwt / auth / crypto / logger）+ utils + 配置加载 | 所有持久化与基础设施 |
| **chameleon-integrations** | 厂商 / 外部实现——LLM 工厂 / embedding / pgvector / reranker / sandbox(docker) / langchain 桥 / observe 落库 handler(call_logs) / plugins registry | 「实现」全落这层 |
| **chameleon-engine** | 编排——graph 工作流引擎 + 节点 / retrieval 检索管线 / eval / a2a / jobs | 工作流与检索的大脑 |
| **chameleon-providers** | provider 抽象（base 协议 / types / registry）+ local（进程内 BaseAgent）+ dify + fastgpt + graph（工作流即 agent） | invoke 的分发层 |
| **chameleon-agents** | 业务级本地 agent（含 `examples/`：echo / rag_qa / triage） | 你的智能体资产 |
| **chameleon-agentkit** | 进程内 agent SDK（`@agent` + `ctx` 隐式拿模型 / KB / trace，多具名模型槽，配置 Schema→自动表单，entry-points 发现） | **写本地 agent 的主入口** |
| **chameleon-api** | 对外 AI 服务 API（agent invoke / knowledge / session / file / task）+ OTLP 摄入 | 公开 `/v1/*` 面 |
| **chameleon-system** | 内部 admin 管理 API（前端面板调） | `/v1/admin/*` 面 |
| **chameleon-app** | 薄 FastAPI 启动器（装配 + lifespan + 中间件 + DI 注入） | 不写业务 |

### graph 工作流引擎的节点家族

`chameleon-engine` 的 graph 引擎内置一整套节点：LLM / KB / Tool / HTTP / Code 沙箱 / Template / 意图分类 / 聚合 / Answer / If-Else / Iteration / Parallel / AgentDebate / HumanInput。graph 既可以在编辑器里拖出来调试，也可以「发布为 agent」，走统一 `POST /v1/invoke`。

### 业务代码 / agent 代码统一从这里 import

```python
# 组件门面（core 提供，内部委托到 integrations 实现）
from chameleon.core.components import llm, embedding, vector, cache, search_kb

# 本地 agent 作者 SDK（写 agent 只 import 这一处）
from chameleon.agentkit import agent, AgentRun, ModelSlot, Opt

# 高级用法（有状态 / 多节点）+ 流事件类型
from chameleon.agentkit import BaseAgent, AgentMetadata, StreamEvent, StreamEventType
```

---

## 三、我要加一个智能体，怎么做？

**先问自己一个问题**：我这个智能体是**本地写代码**实现，还是**在 DIFY/FastGPT 平台拖出来**的（或者用 Chameleon 自带的 graph 工作流编辑器拖）？

```
                  ┌─ 本地写 Python 代码（要灵活控制逻辑 / 工具 / 节点）
我的智能体        │      → 走「本地 agent」路径（A）
                  │
                  ├─ 在 Chameleon graph 编辑器里拖工作流
                  │      → 在编辑器里「发布为 agent」（见 admin 面板 /graphs）
                  │
                  └─ 在 DIFY/FastGPT 平台已经做好了
                         → 走「外部 agent」路径（B）
```

### A. 本地 agent —— `@agent` 装饰器（agentkit）

本地 agent 作者只 import 一处：`chameleon.agentkit`。最小范式是一个 async 函数，从 `ctx` 拿输入、`yield` 文本增量即可，**框架完全解耦——不依赖 LLM / LangChain / LangGraph**。

#### A1. 最小回声（零模型 / 零 KB / 零配置）

```python
# chameleon-agents/examples/echo/src/chameleon/agents/example_echo/agent.py
from __future__ import annotations

from chameleon.agentkit import AgentRun, agent


@agent(
    key="example-echo",
    name="Echo（极简）",
    description="最小 @agent 范式：纯函数回声",
    tags=["example", "minimal"],
)
async def handle(ctx: AgentRun):
    yield f"echo: {ctx.query}"
```

#### A2. RAG 问答（关联 KB + 模型槽）

```python
from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent

SYSTEM_PROMPT = (
    "你是知识库问答助手。优先依据「参考资料」回答；"
    "资料不足时如实说明，不要编造。回答用中文、简洁清晰。"
)


@agent(
    key="example-rag-qa",
    name="RAG 问答",
    description="检索关联知识库 + 模型作答（自动引用）",
    tags=["example", "rag", "kb"],
    models=[ModelSlot("chat", "问答模型")],   # 页面「关联模型」可绑任意已配置模型
    kb=True,                                   # 页面「关联 KB」配的库会被自动检索
)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=5)   # KB 命中自动发引用
    async for delta in ctx.stream(
        slot="chat", system=SYSTEM_PROMPT, context=docs or None, user=ctx.query
    ):
        yield delta
```

要点：
- `models=[ModelSlot("chat", ...)]` 声明模型槽，页面绑定哪个已配置模型由运营在 admin 面板挑。复杂 agent 也能在代码里 `ctx.llm(model=...)` 直接点名。
- `kb=True` 让平台把「关联 KB」自动喂给 `ctx.kb.search`，命中自动转成 citations。
- `config=[Opt("tone", "语气", choices=[...], default="...")]` 这类配置项会自动渲染成前端表单，运营改完即生效，代码里用 `ctx.config["tone"]` 取。

#### A3. 复杂多节点（走 BaseAgent + LangGraph）

需要状态机 / 多节点编排时，从 agentkit re-export 的 `BaseAgent` 起步：

```python
from chameleon.agentkit import AgentMetadata, BaseAgent
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState


class MyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(id="my-agent", name="My", description="...")

    @classmethod
    def build_graph(cls):
        sg = StateGraph(MessagesState)
        # 加节点 / 加边...
        return sg.compile()
    # 不写 astream() —— BaseAgent 默认实现自动用 langchain 桥翻译事件
```

#### 脚手架（5 分钟模板）

```bash
# 1. 建子包（放在 chameleon-agents/ 下）
mkdir -p chameleon-agents/my_agent/src/chameleon/agents/my_agent
mkdir -p chameleon-agents/my_agent/tests
```

```toml
# 2. pyproject.toml
[project]
name = "chameleon-agent-my-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "chameleon-agentkit",
    # 复杂多节点再按需补：
    # "langgraph>=0.2"
]

[tool.uv.sources]
chameleon-agentkit = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chameleon"]
```

```bash
# 3. 装并启动
uv sync --all-packages
uv run uvicorn chameleon.app.main:app --port 7009
```

启动时本地 agent 会被自动发现（扫 `chameleon.agents.*` namespace）并落进 `agents` 表，日志里能看到注册条目。

**外部应用立刻能调**（扁平 invoke，key 即应用身份）：

```bash
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"agent_key": "example-rag-qa", "input": "嗨", "stream": true}'
```

> 如果 key 本身就绑定了某个 agent（`scope_type=app`），`agent_key` 字段可以省略——key 已隐含应用身份（Dify 套路）。

### B. 外部 DIFY/FastGPT agent

外部 HTTP 平台的 agent 走 `config/agents.yaml` 注册（本地 agent 不用写在这里，namespace 自动发现）。启动时这些条目会被 seed 进 `agents` 表。

`config/agents.yaml`：

```yaml
- key: customer-faq           # 对外暴露的 agent key
  provider: dify              # 或 fastgpt
  description: 客服 FAQ
  endpoint: ${baseurl:dify-default}   # 引用 baseurl.json，或写死 URL
  app_id: ${env:DIFY_FAQ_APP_ID}      # 仅记录用（DIFY 靠 api_key 隔离 app）
  api_key_env: DIFY_FAQ_KEY           # 实际 api key 从这个 env 名字取，不落 DB
  mode: chat                          # chat / workflow
```

`config/.env`：

```env
DIFY_FAQ_APP_ID=abcd-1234
DIFY_FAQ_KEY=app-xxxxxxxxxxx
```

重启服务后，调用方式**和本地 agent 完全一样**：

```bash
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"agent_key": "customer-faq", "input": "如何退货", "stream": true}'
```

DIFY 端的会话变量 / RAG 上下文 / 知识库都正常工作——Chameleon 把 `session_id` 双写并透传。

---

## 四、配置真实 LLM（实操）

`ctx.stream(...)` / `ctx.llm(...)` / `chameleon.core.components.llm()` 取到的 LLM 客户端，背后由 `config/model.json` 配置。

### AI 配置：`config/model.json`

```json
{
  "cases": {
    "llm": "qwen-plus",
    "embedding": "text-embedding-3-small"
  },
  "providers": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-..."
    },
    "deepseek": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-..."
    },
    "qwen": {
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-..."
    }
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

`api_key` 直接写在 `providers.<name>.api_key`——`model.json` 已被 `.gitignore` 排除，不会泄漏。

> 通义千问用 OpenAI **兼容模式**（`/compatible-mode/v1`），不是原生 DashScope SDK。LLM 工厂基于 `langchain-openai`，所有 OpenAI 兼容厂商都能直接用。
>
> 想做生产级模型聚合 / 路由（多 key 负载、限流、回退），用**外部 oneapi**——Chameleon 不再内置渠道矩阵路由。

### 中间件配置：`config/component.json`

数据库 / Redis 等连接信息：

```json
{
  "database": {
    "type": "postgres",
    "driver": "asyncpg",
    "host": "127.0.0.1",
    "port": 8103,
    "user": "collector",
    "password": "030317Archer",
    "db": "chameleon"
  },
  "redis": {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0,
    "password": ""
  }
}
```

`inventory.database_url()` 自动从这里拼成 `postgresql+asyncpg://collector:xxx@127.0.0.1:8103/chameleon`。`type: postgres` 自动映射为 SQLAlchemy 的 `postgresql` dialect。向量检索用 **pgvector**，所以 DB 必须是带 pgvector 扩展的 Postgres。

### `.env` 的归宿

`.env` 仅留**部署级 override**——单机场景下可以**几乎为空**：

```env
CHAMELEON_INSTANCE_ID=0

# 按需 override（容器化部署常用）
# LOG_LEVEL=DEBUG
# DATABASE_URL=postgresql+asyncpg://...    ← override component.json database.*
```

`agents.yaml` 引用的外部 agent api_key（如 `DIFY_FAQ_KEY`）也放 `.env`，但**不再**用 `.env` 放 LLM 厂商 key（那些已经在 `model.json` 里）。

### 验证

最快方式 —— Python 直调：

```bash
uv run python -c "
import asyncio
from chameleon.core.components import llm

async def main():
    chat = llm()
    resp = await chat.ainvoke([{'role':'user','content':'你好'}])
    print(resp.content)

asyncio.run(main())
"
```

### 切换厂商怎么做

从 Qwen 切到 DeepSeek：

1. `config/model.json` 把 `cases.llm` 改成 `"deepseek-chat"`
2. 确保 `providers.deepseek.api_key` 已填
3. 重启 Chameleon

**业务代码 / agent 代码完全不动**——`llm()` 自动取新模型。

### 配置文件总览

| 文件 | 内容 | 谁会改 |
|---|---|---|
| `model.json` | AI 全包（cases / providers / models） | **AI 工程师** —— 调模型、换 LLM 厂商时 |
| `component.json` | DB / Redis 等中间件连接 | **运维** —— 部署 / 迁移时 |
| `chameleon.json` | 业务参数（log_level / session / knowledge / stream / timeouts） | **应用开发** —— 调业务行为时 |
| `baseurl.json` | 外部 agent 平台 URL（DIFY/FastGPT 实例地址）—— 仅给 `agents.yaml` `${baseurl:x}` 占位符引用 | 接外部 agent 时 |
| `agents.yaml` | 外部 agent 注册条目（DIFY/FastGPT app） | 加外部 agent 时 |
| `.env` | 部署级 env override（容器化必备；本地几乎空） | **运维** —— 容器化部署时 |

---

## 五、外部应用怎么接 Chameleon？

### Step 0：先有一个 admin key

```bash
uv run chameleon init-admin
# 输出里有一行明文 KEY（仅一次回显，立即保存）：chm_xxxxxxxx
```

### Step 1：用 admin key 发一个 app key

API key 有三种作用域（前缀对应）：

| `scope_type` | 前缀 | 含义 | `scope_ref` |
|---|---|---|---|
| `global` | `chm_` | 通吃（admin / 跨 agent / 跨 KB） | 空 |
| `app` | `app-` | 绑定某个 agent / 应用 | agent_key |
| `kb` | `kbs-` | 绑定某个知识库 | kb_key |

```bash
ADMIN_KEY="chm_xxx..."   # 来自 chameleon init-admin 输出

curl -X POST http://localhost:7009/v1/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"我的项目","scope_type":"app","scope_ref":"customer-faq"}'

# 返回明文 key（plain_key），仅这一次回显
```

### Step 2：把 plain_key 配到你那个应用的环境变量

```env
CHAMELEON_API_KEY=app-xxxxxxxxxxxxxxxxxxxx
CHAMELEON_URL=http://localhost:7009
```

### Step 3：在应用代码里调（任何语言都行——它就是个 HTTP API）

> 也可以直接用官方 SDK：Python `chameleon-sdk`（httpx sync+async，含 `@trace` / `patch_openai` / `patch_all`）或 TypeScript `@chameleon/sdk`。下面是裸 HTTP 示例。

```python
# Python 示例
import os
import httpx

async def ask_ai(text: str, session_id: str | None = None):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{os.environ['CHAMELEON_URL']}/v1/invoke",
            headers={"Authorization": f"Bearer {os.environ['CHAMELEON_API_KEY']}"},
            json={
                "agent_key": "customer-faq",   # key 已绑 agent 时可省略
                "input": text,
                "session_id": session_id,
                "stream": False,
            },
            timeout=60,
        )
    body = r.json()
    if not body["success"]:
        raise Exception(f"AI error: {body['message']}")
    return body["data"]["answer"], body["data"]["session_id"]
```

```javascript
// JavaScript / TypeScript 示例
async function askAi(text, sessionId = null) {
  const r = await fetch(`${CHAMELEON_URL}/v1/invoke`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${CHAMELEON_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      agent_key: "customer-faq",
      input: text,
      session_id: sessionId,
      stream: false,
    }),
  });
  const body = await r.json();
  if (!body.success) throw new Error(body.message);
  return { answer: body.data.answer, sessionId: body.data.session_id };
}
```

**SSE 流式**（前端打字机效果）：

```javascript
const r = await fetch(`${CHAMELEON_URL}/v1/invoke`, {
  method: "POST",
  headers: { /* ... */ },
  body: JSON.stringify({ agent_key: "customer-faq", input: text, stream: true }),
});

const reader = r.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  // 解析 SSE 块（event: xxx\ndata: {...}\n\n）
  ...
}
```

> 想兼容现有 OpenAI 客户端？Chameleon 还提供 **OpenAI 兼容端点**（`/v1` 下），直接把 `base_url` 指过来即可。

---

## 六、一个实操：5 分钟做「客服 FAQ」agent

**场景**：你公司有一个 FAQ 文档，想做个客服机器人，让你的网站调它回答用户问题。

### Step 1：建知识库 + 灌文档

KB 走 `/v1/kb`，由 key 隐含 KB 身份（`scope_type=kb` 的 key 绑定某库；`global` key 需在 body / query 带 `kb_key`）。

```bash
KB_KEY="kbs-xxxxxxx"   # 绑定 company-faq 的 kb 作用域 key

# 灌一段 FAQ 文本（异步处理）
curl -X POST "http://localhost:7009/v1/kb/documents" \
  -H "Authorization: Bearer $KB_KEY" \
  -d '{
    "title": "退货政策",
    "source_type": "text",
    "content": "客户在收到商品 7 天内可申请退货。退货商品必须保持原包装..."
  }'

# 返回 {task_id, document_id, status: "queued"}
# 轮询任务进度
curl "http://localhost:7009/v1/tasks/<task_id>" \
  -H "Authorization: Bearer $KB_KEY"
# → {status: "success", progress: 100, ...}
```

> KB 支持多种 Collection 类型（generic / FAQ / Wiki / API 各自 chunker）；检索是 **hybrid**（vector + BM25 + RRF + filter + reranker），还支持元数据字段过滤召回、VLM 图片 caption、一致性扫描。这些在 admin 面板里配。

### Step 2：直接搜（不用 agent，纯 RAG）

```bash
curl -X POST "http://localhost:7009/v1/kb/search" \
  -H "Authorization: Bearer $KB_KEY" \
  -d '{"query":"怎么退货","top_k":3}'
```

返回 top 3 命中的 chunks。

### Step 3：用 RAG agent 做对话（自动引用）

直接复用上面 A2 的 `example-rag-qa`（页面把它的 KB 槽绑到 `company-faq`）：

```bash
curl -X POST http://localhost:7009/v1/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"agent_key":"example-rag-qa","input":"怎么退货","stream":false}'
```

返回里 `data.citations` 包含命中的 FAQ chunks，你的网站可以渲染「参考依据」块。

### Step 4：写一个真正的 FAQ agent（生产用）

仿照 A2，在 `chameleon-agents/faq/` 写一个带 `models` + `kb=True` 的 `@agent`，按需在 `ctx.complete(...)` 里精修 system prompt、加意图判断分支。部署后调用方式不变：`POST /v1/invoke`（`agent_key=faq`）。

---

## 七、当前对外 API 面（速查）

公开（`/v1/*`，业务方调）：

| 前缀 | 干啥 |
|---|---|
| `POST /v1/invoke` · `GET /v1/info` | 统一 agent 调用 + 当前 key 绑定信息 |
| `/v1/sessions` | 会话列表 / 详情 / 消息 / 删除 |
| `/v1/kb` | 知识库元信息 / 文档 CRUD + ingest / search |
| `/v1/embed` | 嵌入式接入（widget / form） |
| `/v1/files` | 文件上传 / 引用 |
| `/v1/tasks/{id}` | 异步任务进度 |
| `/v1/otel`（OTLP） | trace 摄入 |
| `/v1/auth` | 鉴权 |
| `/v1`（OpenAI 兼容） | 兼容现有 OpenAI 客户端 |

内部 admin（`/v1/admin/*`，前端面板调）：`agents` · `api-keys` · `app-templates` · `kbs` · `graphs` · `models` · `providers` · `datasets` · `eval-jobs` · `eval-templates` · `plugins` · `marketplace` · `tools` · `schemas` · `scores` · `search` · `session-files` · `settings` · `users` · `roles` · `permissions` · `audit-logs` · `dashboard` · `playground` · `embed-configs`。

---

## 八、可观测（Trace / Session）

Chameleon 的可观测是 **LangSmith 化**的：

- `call_logs` 是**唯一 trace 真相源**；一次调用是一棵 trace 树，由嵌套 observation（span + generation）组成。
- graph 工作流的每个节点发 span 进同一棵 trace 树；根行做 rollup（汇总 model / token / cost）。
- 前端把可观测拆成 **Trace · Session 两个 tab**。

排查一个 agent 报错的三层抓手：

1. uvicorn stdout（loguru 格式，含 request_id）
2. `logs/chameleon.log` 文件
3. admin 面板的 Trace / Session tab，或 dashboard / audit-logs

---

## 九、前端 / 工具链 / SDK / 部署

**前端**：React 19 + Vite + TS strict + Tailwind v4 + Radix + TanStack Query + Zustand + ReactFlow。**4 个导航域：工作台 / 知识库 / 观测 / 设置**。源码在 `frontend/src/{core(共享), system/<module>(自包含), api-docs}`。dev 端口默认 **6006**。

**后端工具链**：uv（workspace）· ruff · pytest · **import-linter**（分层架构护栏，2 契约常驻 GREEN）。
**前端工具链**：yarn + vite · eslint · tsc。

**SDK**：Python `chameleon-sdk`（httpx sync+async，`@trace` / `patch_openai` / `patch_all`）· TypeScript `@chameleon/sdk`。trace 摄入走 OTLP HTTP。

**部署**：Docker + Compose，多阶段镜像，`docker/` 三区（images / containers / scripts）。后端默认端口 **7009**。

---

## 十、最常见的几个问题

**Q: 我有个 LangChain agent（不是 LangGraph），能接入吗？**
A: 可以。简单链式直接在 `@agent` 函数里跑你的 Runnable，把输出 `yield` 出来即可；复杂的走 `BaseAgent` + `build_graph()`，把 Runnable 塞进单节点：

```python
def build_graph():
    sg = StateGraph(MessagesState)
    sg.add_node("run", lambda s: {"messages": [my_runnable.invoke(s["messages"])]})
    sg.add_edge(START, "run")
    sg.add_edge("run", END)
    return sg.compile()
```

**Q: 我的应用要会话历史，但用户不想让历史落在 Chameleon 这边，怎么办？**
A: 调 invoke 时传 `input: list[Message]` 而不是 `str`——这样 Chameleon 不会从 session 取历史，由客户端自管。`input` 是 `str` 时才会按 `session_id` + `user` 拉历史。

**Q: 多个终端用户共用一个 app key，会话怎么隔离？**
A: invoke 时传 `user`（终端用户外部标识，对应 Dify/OpenAI 协议的 `user`）。`session_id` 续接要求同 agent + 同 `user`，历史按 `user` 隔离，计费也能按用户统计。

**Q: 我的 DIFY 应用更新了，怎么让 Chameleon 知道？**
A: DIFY 端的更新（agent 内部逻辑、prompts、知识库）**Chameleon 完全不感知**——它只是个 HTTP 转发。除非你改了 endpoint 或 API key，否则不用动 Chameleon。

**Q: 我要换 LLM 厂商（如 OpenAI 换成 Qwen）怎么做？**
A: 改 `config/model.json` 的 `cases.llm` 字段 + 确保对应 `providers.<name>.api_key` 已填 + 重启。**不动业务代码**。

---

## 十一、下一步

1. 跟着「第六节实操」做一遍——把 FAQ agent 跑通
2. 看 `docs/extension-guide.md` —— 扩展场景 step-by-step
3. 看 `docs/architecture.md` —— 10 包分层与 import-linter 护栏的来龙去脉

---

## 还是看不懂？

直接告诉我哪里没讲清楚 —— 文档为人服务，不为完整服务。
