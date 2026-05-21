# Chameleon 入门指南（使用者视角）

> 这份文档不讲怎么造 Chameleon，讲**你要用它做什么**。

---

## 一、Chameleon 是干嘛的

```
你的某个应用（Web / 脚本 / Slack 机器人 / 移动 App）
        ↓ HTTP 调用
   ┌─────────────────┐
   │   Chameleon     │   ← 你部署的这个项目（个人 AI 中枢）
   │  统一 invoke   │
   └────┬────────────┘
        ↓ 内部分发
   ┌────┴────┬─────────┬─────────┐
   ↓         ↓         ↓         ↓
 本地       DIFY      FastGPT    ...
 LangGraph  HTTP      HTTP       将来
```

**核心承诺**：你的应用只学**一个**调用方式（`POST /v1/agents/{key}/invoke`），背后的智能体来源（自己写的 / DIFY 编排的 / FastGPT 编排的 / 未来 Coze 的）随便换，**消费者代码不动**。

**对 agent 作者的承诺**：本地 agent 框架**不锁死编排库**——你可以用：
- 纯 Python 异步生成器（最自由，可接 Anthropic SDK / 自研 client）
- LangChain Runnable / LCEL（链式简单调用）
- LangGraph CompiledGraph（复杂多节点）
- 三种混合

三种范式产出的事件流统一为 Chameleon `StreamEvent`，对客户端完全透明。

---

## 二、项目模块大白话对照（已系统融合 sage 习惯）

如果你以前看 sage，下面这表帮你快速建立映射。**🟢 标记 = v1 已对齐 sage 习惯**：

| sage 里的概念 | Chameleon 里的位置 | 干嘛的 |
|---|---|---|
| 🟢 `sage-core/components/llms/` | `chameleon-core/.../core/components/llms/`（BaseLLM + ChatQwen/ChatDeepSeek/ChatOpenAI + LLMFactory） | LLM 客户端工厂（OpenAI 兼容） |
| 🟢 `sage-core/components/embeddings/` | `chameleon-core/.../core/components/embeddings/`（DashScopeEmbeddings/OpenAIEmbeddings 别名） | embedding 客户端工厂 |
| 🟢 `sage-core/components/vector/` | `chameleon-core/.../core/components/vector/`（VectorStore + PgVectorStore） | 向量存储抽象 + pgvector |
| 🟢 `sage-core/components/cache/cache_manager.py` | `chameleon-core/.../core/components/cache/`（CacheManager 单例 + diskcache） | 通用 kv 缓存 |
| 🟢 `sage-core/components/inventory.py` | `chameleon-core/.../core/components/inventory.py`（llm/embedding/vector/cache/search_kb 顶层函数） | 全局组件具名访问点 |
| 🟢 `sage-core/base/base_agent.py` + agent_router + agent_context | `chameleon-core/.../core/base/`（BaseAgent + AgentRouter + AgentContext + AgentMetadata + AgentConfigOption） | agent 基类 + 注册中心 |
| 🟢 `sage-core/function/` (prompts + chain) | `chameleon-core/.../core/function/`（占位 + README 范式） | prompt 模板 + Runnable 工厂 |
| 🟢 `sage-core/complex/utils/convert_util.py` | `chameleon-core/.../core/utils/convert.py` | ORM↔dict/Pydantic |
| 🟢 `sage-core/complex/utils/crypto_util.py` | `chameleon-core/.../core/utils/crypto.py` | AES-256-GCM 敏感数据加密 |
| 🟢 `sage-core/complex/utils/snowflake.py` | `chameleon-core/.../core/utils/snowflake.py` | 雪花 ID |
| `sage-core/complex/config/` | `chameleon-core/.../core/config/`（pydantic-settings + BaseSettings + inventory） | 配置 |
| `sage-core/complex/response/` | `chameleon-core/.../core/response.py` + `exceptions.py` | Result + 业务错误码 |
| `sage-core/components/skill/` | （v1 占位 `function/`；v0.2 接） | 技能注册 |
| `sage-core/components/audio/` | （v1 不做） | 语音模型 |
| `sage-core/components/memory/` | 部分由 conversations + messages 表实现；ES/Redis v1 不做 | 历史 |
| `sage-system/modules/chat/` | `chameleon-app/.../modules/agent/` | HTTP 入口 + 会话编排 |
| `sage-agents/data_qa_v2/` | `chameleon-agents/<your_agent>/` 子包 | 具体 agent 实现 |
| `sage-agents/data_qa_v2/deps_factory.py` | 你 agent 子包里的 `deps_factory.py` | 依赖注入工厂 |
| `sage-agents/data_qa_v2/function/graph/` | 你 agent 子包里的 `function/graph/`（含 `nodes/`） | LangGraph 图与节点 |
| `sage` AiModel 表 DB-driven 配置 | Chameleon model.json 配置文件 | 理念不同：sage 入 DB，chameleon 走配置 |

### v1 完整顶层 imports 视图

业务代码 / agent 代码统一从这里 import：

```python
# 组件（仿 sage components/inventory）
from chameleon.core.components import llm, embedding, vector, cache, search_kb

# LLM 多厂商类（仿 sage components/llms/base.py）
from chameleon.core.components.llms import BaseLLM, ChatQwen, ChatDeepSeek, ChatOpenAI

# BaseAgent 体系（仿 sage core/base）
from chameleon.core.base import (
    BaseAgent, AgentMetadata, AgentConfigOption, AgentContext, agent_router,
)

# 工具（仿 sage complex/utils）
from chameleon.core.utils import model_to_dict, next_id, next_session_id
from chameleon.core.utils.crypto import encrypt, decrypt, get_or_decrypt
```

### 与 sage 的关键差异（务必知道）

1. **配置存哪**：sage 走 DB（`ai_models` 表 + AiModel ORM）；chameleon 走 `config/model.json`——理念是"个人项目配置即代码"，DB-driven 配置等多用户场景再加
2. **agent 注册**：sage 用 `agent_router.register(MyAgent)` 显式调用；chameleon 通过 namespace 扫描自动注册（写 `chameleon-agents/<key>/` 子包即可），同时 BaseAgent 子类也会自动注册到 `agent_router`
3. **流式协议**：sage agent 自己产 SSE event；chameleon 通过 LangGraphProvider 统一 `astream_events` 自动翻译，agent 只写 graph 节点
4. **session 概念**：sage 有 space_id / user_id 多租户；chameleon v1 简化为 app_id 单租户（多 app 通过 API key 隔离）

### v1 故意没做的（v0.2+ 按需）

- **sage skill registry**：v1 用 LangGraph node 直接组装即可，等真需要跨 agent 复用"技能"才接
- **AiModel DB 表**：v1 走 model.json 配置文件，等需要 admin UI 改模型时再入 DB
- **sage's chat workflow event_types**（INTENT/SQL/DATA 等业务级事件）：chameleon 用统一 StreamEvent 抽象层级；业务级语义通过 `step.thinking` / `step.output` / `metadata` 字段携带
- **audio / memory(ES) / analytics**：v1 不做

---

## 三、我要加一个智能体，怎么做？

**先问自己一个问题**：我这个智能体是**自己写代码**实现，还是**在 DIFY/FastGPT 平台拖出来**的？

```
                  ┌─ 自己写 Python 代码（要灵活控制 LangGraph 图、节点逻辑、工具）
我的智能体       │      → 走"本地 LangGraph"路径（A）
                  │
                  └─ 在 DIFY/FastGPT 平台已经做好了
                         → 走"外部 agent"路径（B）
```

### A. 自己写的本地 agent —— **三种范式任选**

★ Chameleon 本地 agent **不强制 LangGraph**。任选一种范式：

| 范式 | 何时用 | 依赖 | 样板 |
|---|---|---|---|
| **A1. 纯 Python async generator** | 简单逻辑 / 用 Anthropic SDK / 想极致灵活 | 仅 chameleon-core + providers-base | `chameleon-agents/examples/echo_native/` |
| **A2. LangChain Runnable (LCEL)** | `prompt \| llm \| parser` 链式调用 | + langchain-core | `chameleon-agents/examples/echo_runnable/` |
| **A3. LangGraph CompiledGraph** | 多节点状态机 / 复杂编排 | + langgraph | `chameleon-agents/examples/echo_langgraph/` |

**统一契约**：三种范式产出的都是 Chameleon `StreamEvent`，对客户端**完全透明**——你的应用一行代码不改就能切换 agent 实现。

#### A1. 纯 Python async generator（最自由）

```python
# chameleon-agents/my_agent/src/chameleon/agents/my_agent/agent.py
from collections.abc import AsyncIterator
from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import InvokeContext, StreamEvent, StreamEventType


class MyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(id="my-agent", name="My", description="...")

    @classmethod
    async def astream(cls, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        # 完全自由：调任何 LLM SDK，自己 yield 任意 event
        text = ctx.input if isinstance(ctx.input, str) else ctx.input[-1].content

        yield StreamEvent(type=StreamEventType.step,
                          data={"name": "thinking", "status": "success"})

        # 比如调 Anthropic SDK 流式：
        # async for chunk in anthropic_client.messages.stream(...):
        #     yield StreamEvent(type=StreamEventType.delta, data={"text": chunk.text})

        for ch in f"echo: {text}":
            yield StreamEvent(type=StreamEventType.delta, data={"text": ch})
```

```python
# __init__.py
from chameleon.agents.my_agent.agent import MyAgent
__all__ = ["MyAgent"]
```

#### A2. LangChain Runnable / LCEL

```python
# agent.py
from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.core.components import llm
from langchain_core.prompts import ChatPromptTemplate


class MyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(id="my-agent", name="My", description="...")

    @classmethod
    def build_runnable(cls):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个有用的助手。"),
            ("placeholder", "{history}"),
            ("user", "{input}"),
        ])
        return prompt | llm()

    # 不写 astream() —— BaseAgent 默认实现自动用 from_runnable() 桥
```

#### A3. LangGraph CompiledGraph（复杂多节点）

```python
# agent.py
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState
from chameleon.core.base import AgentMetadata, BaseAgent


class MyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(id="my-agent", name="My", description="...")

    @classmethod
    def build_graph(cls):
        sg = StateGraph(MessagesState)
        # 加节点 / 加边...
        return sg.compile()

    # 不写 astream() —— BaseAgent 默认实现自动用 from_langgraph_graph() 桥
```

或者混合：自己 override `astream()` 并在内部既用 LangGraph 又自己 yield 收尾事件——完全自由组合。

#### 三种范式共用的脚手架（5 分钟模板）

```bash
# 1. 建子包
mkdir -p chameleon-agents/my_agent/src/chameleon/agents/my_agent
mkdir -p chameleon-agents/my_agent/tests
```

```toml
# 2. pyproject.toml（按范式选依赖）
[project]
name = "chameleon-agent-my-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "chameleon-core",
    "chameleon-providers-base",
    # 按范式选：
    # "langgraph>=0.2"        # 范式 A3
    # "langchain-core>=0.3"   # 范式 A2（chameleon-core 已含 langchain-openai，按需补）
    # 范式 A1 啥都不用加
]

[tool.uv.sources]
chameleon-core = { workspace = true }
chameleon-providers-base = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chameleon"]
```

```bash
# 3. 装并启动
uv sync --all-packages
uv run uvicorn chameleon.app.main:app
```

启动日志自动出现（`mode` 字段标识哪种范式）：
```
agent registered (local) | key=my-agent | module=chameleon.agents.my_agent | mode=BaseAgent
```

**外部应用立刻能调（无论你用哪种范式）**：

```bash
curl -X POST http://localhost:8000/v1/agents/my-agent/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input": "嗨", "stream": true}'
```

➡️ **复杂 agent 怎么组织？** 看下面"sage 风格范式"章节（适用所有三种范式）。

### B. 外部 DIFY/FastGPT agent

**最少 3 分钟，全是配置**：

`config/agents.yaml`：

```yaml
- key: customer-faq           # 对外暴露的 agent key
  provider: dify              # 或 fastgpt
  description: 客服 FAQ
  endpoint: ${baseurl:dify-default}   # 或写死 URL
  app_id: ${env:DIFY_FAQ_APP_ID}      # DIFY 应用 ID
  api_key_env: DIFY_FAQ_KEY           # api key 从这个 env 名字取
  mode: chat                          # chat / workflow
```

`config/.env`：

```env
DIFY_FAQ_APP_ID=abcd-1234
DIFY_FAQ_KEY=app-xxxxxxxxxxx
```

重启服务：

```
agent registered (yaml) | key=customer-faq | provider=dify
```

调用方式**和本地 agent 完全一样**：

```bash
curl -X POST http://localhost:8000/v1/agents/customer-faq/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input": "如何退货", "stream": true}'
```

DIFY 端的会话变量 / RAG 上下文 / 知识库都正常工作——Chameleon 把 `conversation_id` 双写并透传。

---

## 四、复杂本地 agent 范式（吸收 sage data_qa_v2 模式）

你 sage 里 `data_qa_v2` 的拆分非常清晰：

```
data_qa_v2/
├── agent.py                    ← 顶层包装（metadata + process）
├── deps_factory.py             ← 每请求构造依赖（LLM/db/services）
└── function/graph/
    ├── chat_workflow.py        ← 图组装 + 路由
    ├── state.py                ← AgentState typed
    └── nodes/
        ├── classify_intent.py
        ├── load_skill.py
        ├── plan_proposal.py
        └── ...                 ← 一节点一文件
```

**这个范式可以直接搬到 Chameleon**，只需要去掉 `agent.py` 那层（v1 Chameleon 不需要 BaseAgent 包装——`build_graph()` 直接被 LangGraphProvider 调用）。

### 推荐结构（复杂 agent）

```
chameleon-agents/my_complex/
├── pyproject.toml
├── tests/
│   └── nodes/...               ← 每个节点单测
└── src/chameleon/agents/my_complex/
    ├── __init__.py             ← export build_graph + AGENT_META
    ├── deps_factory.py         ← 构造 LLM / db / vector 等依赖
    ├── state.py                ← AgentState typed dict
    └── function/
        └── graph/
            ├── workflow.py     ← StateGraph 组装 + 路由
            └── nodes/
                ├── classify.py
                ├── retrieve.py
                ├── generate.py
                └── ...
```

### 关键模式 1：deps_factory（依赖注入）

避免节点直接调全局 —— **每次请求构造一组 deps，注入到 graph**：

```python
# deps_factory.py
from chameleon.core.embedding import get_embedding_client
from chameleon.core.knowledge import search_kb
from chameleon.core.vector import get_store

def build_deps(*, app_id: str, kb_key: str | None = None) -> dict:
    """每个请求一份；可以注入 mock 做单测"""
    return {
        "embed": get_embedding_client(),
        "vector": get_store(),
        "search_kb": search_kb,
        "kb_key": kb_key,
        # 你的 SQL executor / 业务 service / LLM client
    }
```

### 关键模式 2：state.py typed AgentState

```python
# state.py
from typing import TypedDict, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str | None
    citations: list[dict]
    kb_key: str | None
    # 你的业务字段
```

### 关键模式 3：节点接收 deps + state，返 state 差分

```python
# nodes/retrieve.py
async def retrieve_node(state: AgentState, deps: dict) -> dict:
    query = state["messages"][-1].content
    hits = await deps["search_kb"](
        deps["kb_key"],
        query,
        top_k=5,
        min_score=0.3,
    )
    return {
        "citations": [
            {"source": f"chunk:{h.id}", "score": h.score, "snippet": h.content}
            for h in hits
        ]
    }
```

### 关键模式 4：build_graph 注入 deps

```python
# function/graph/workflow.py
from functools import partial
from langgraph.graph import END, START, StateGraph

from chameleon.agents.my_complex.deps_factory import build_deps
from chameleon.agents.my_complex.state import AgentState
from chameleon.agents.my_complex.function.graph.nodes.classify import classify_node
from chameleon.agents.my_complex.function.graph.nodes.retrieve import retrieve_node
from chameleon.agents.my_complex.function.graph.nodes.generate import generate_node

def _route_after_classify(state: AgentState) -> str:
    return "retrieve" if state["intent"] == "qa" else "generate"

def build_workflow():
    """sync function（A4 裁决）。LangGraphProvider 首次 invoke 时调一次。

    注意：build 时不知道 app_id / kb_key 等运行时上下文，
         所以 deps_factory 在节点内部按需调（参考下方 partial 用法）。
    """
    deps_holder = {}  # 闭包持 deps

    async def with_deps(node_fn, state):
        if not deps_holder:
            # 首次构建 deps（这里可以从 context_vars 取上下文）
            deps_holder["d"] = build_deps()
        return await node_fn(state, deps_holder["d"])

    sg = StateGraph(AgentState)
    sg.add_node("classify", partial(with_deps, classify_node))
    sg.add_node("retrieve", partial(with_deps, retrieve_node))
    sg.add_node("generate", partial(with_deps, generate_node))

    sg.add_edge(START, "classify")
    sg.add_conditional_edges("classify", _route_after_classify, {
        "retrieve": "retrieve",
        "generate": "generate",
    })
    sg.add_edge("retrieve", "generate")
    sg.add_edge("generate", END)
    return sg.compile()
```

```python
# __init__.py
from chameleon.agents.my_complex.function.graph.workflow import build_workflow as build_graph

AGENT_META = {"key": "my-complex", "description": "...", "version": "0.1"}
```

### 关键模式 5：让 citations 自动出现在响应里

LangGraphProvider 翻译层已经做了：**graph 最终 state 里的 `citations` 字段会被自动 emit 为 citation 事件**。你只要在 state 里放好即可，外部应用收到的 invoke 响应自动含 `citations: [...]`。

### 关键模式 6：调 LLM（v1 简化）

v1 Chameleon 没把 sage 的 `BaseLLM` + 多厂商类搬过来，但你可以**直接用 langchain_openai**（sage 也是这么做的，`BaseLLM` 继承 `BaseChatOpenAI`）：

```python
# deps_factory.py
from langchain_openai import ChatOpenAI
from chameleon.core.config import inventory

def make_llm():
    """读 config/model.json + .env 构造 LLM client"""
    name = inventory.case_llm()  # 默认模型名
    cfg = inventory.llm_model_config(name)
    base_url, api_key = inventory.llm_provider_credential(cfg["provider"])
    return ChatOpenAI(
        model=name,
        openai_api_base=base_url,
        openai_api_key=api_key,
        temperature=cfg.get("temperature", 0.7),
        max_tokens=cfg.get("max_tokens"),
        stream_usage=True,
    )
```

> **想要 sage 完整 `BaseLLM` 体系？** 把 `sage-core/components/llms/` 整个目录 copy 到 `chameleon-core/.../core/components/llms/`，去掉 sage db 模型依赖，改用 chameleon `inventory.llm_provider_credential()`。这是 v0.2 候选项。

### 关键模式 7：节点单测

每个节点写一个测试，注入 stub deps：

```python
# tests/nodes/test_retrieve.py
async def test_retrieve_returns_citations():
    fake_hits = [type("Hit", (), {
        "id": 1, "score": 0.9, "content": "chunk text"
    })()]
    deps = {
        "search_kb": lambda *a, **kw: fake_hits,
        "kb_key": "test-kb",
    }
    state = {"messages": [HumanMessage("query")]}
    result = await retrieve_node(state, deps)
    assert result["citations"][0]["score"] == 0.9
```

---

## 四点五、配置真实 LLM（实操）—— sage 风格

第三章的范式 A2/A3 都会用 `chameleon.core.components.llm()` 取 LLM 客户端。
**所有 AI 相关配置全在一个文件**：`config/model.json`（sage 习惯：AI 全包）。

### 全部 AI 配置：`config/model.json`

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
      "api_key": "sk-7f51fa77603e4c0da2b54fad614deb94"
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

**就这一个文件**。`api_key` 直接写在 `providers.<name>.api_key`——`model.json` 已被 `.gitignore` 排除，不会泄漏。

> 与 sage 的差异：sage 用 `keys: {openai: {OPENAI_API_KEY: "sk-..."}}` 命名空间嵌套；
> chameleon 简化为 `providers.<name>` 内 `api_key + base_url` 平铺——更直观，与
> `BaseLLM(api_key=, api_base=)` 参数一一对应。

注意：通义千问用 OpenAI **兼容模式**（`/compatible-mode/v1`），不是原生 DashScope SDK。BaseLLM 继承 `langchain_openai.ChatOpenAI`，所有 OpenAI 兼容厂商都能直接用。

### 中间件配置：`config/component.json`

数据库 / Redis 等连接信息（仿 sage `component.json`）：

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

`inventory.database_url()` 自动从这里拼成 `postgresql+asyncpg://collector:xxx@127.0.0.1:8103/chameleon`。`type: postgres` 自动映射为 SQLAlchemy 的 `postgresql` dialect。

### `.env` 的归宿

`.env` 仅留**部署级 override**——单机场景下可以**几乎为空**：

```env
CHAMELEON_INSTANCE_ID=0

# 按需 override（容器化部署常用）
# LOG_LEVEL=DEBUG
# DATABASE_URL=postgresql+asyncpg://...    ← override component.json database.*
```

`agents.yaml` 引用的外部 agent api_key（如 `DIFY_FAQ_KEY`）也可以放 .env，但**不再**用 .env 放 LLM 厂商 key（那些已经在 model.json 里）。

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

或者用内置 `qwen-chat` agent：

```bash
curl -X POST http://localhost:8000/v1/agents/qwen-chat/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input":"你好","stream":true}'
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
| `baseurl.json` | 外部 agent 平台 URL（DIFY/FastGPT 实例地址）—— 仅给 agents.yaml `${baseurl:x}` 占位符引用 | 接外部 agent 时 |
| `agents.yaml` | 外部 agent 注册条目（DIFY/FastGPT app） | 加外部 agent 时 |
| `.env` | 部署级 env override（容器化必备；本地几乎空） | **运维** —— 容器化部署时 |

---

## 五、外部应用怎么接 Chameleon？

**Step 1**：管理员（你自己）用 admin key 发一个 app key：

```bash
ADMIN_KEY="chm_xxx..."   # 来自 chameleon init-admin 输出

curl -X POST http://localhost:8000/v1/admin/api-keys \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"my-side-project","name":"我的项目","scopes":[]}'

# 返回明文 key（plain_key），仅这一次回显
```

**Step 2**：把 plain_key 配到你那个应用的环境变量：

```env
CHAMELEON_API_KEY=chm_xxxxxxxxxxxxxxxxxxxx
CHAMELEON_URL=http://localhost:8000
```

**Step 3**：在应用代码里调（任何语言都行——它就是个 HTTP API）：

```python
# Python 示例
import httpx

async def ask_ai(text: str, session_id: str | None = None):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{os.environ['CHAMELEON_URL']}/v1/agents/customer-faq/invoke",
            headers={"Authorization": f"Bearer {os.environ['CHAMELEON_API_KEY']}"},
            json={
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
  const r = await fetch(`${CHAMELEON_URL}/v1/agents/customer-faq/invoke`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${CHAMELEON_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ input: text, session_id: sessionId, stream: false }),
  });
  const body = await r.json();
  if (!body.success) throw new Error(body.message);
  return { answer: body.data.answer, sessionId: body.data.session_id };
}
```

**SSE 流式**（前端打字机效果）：

```javascript
const r = await fetch(`${CHAMELEON_URL}/v1/agents/customer-faq/invoke`, {
  method: "POST",
  headers: { /* ... */ },
  body: JSON.stringify({ input: text, stream: true }),
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

---

## 六、一个实操：5 分钟做"客服 FAQ"agent

**场景**：你公司有一个 FAQ 文档，想做个客服机器人，让你的网站调它回答用户问题。

### Step 1：建知识库 + 灌文档

```bash
APP_KEY="chm_xxxxxxx"

# 建 KB
curl -X POST http://localhost:8000/v1/knowledge \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"kb_key":"company-faq","name":"客服 FAQ"}'

# 灌一段 FAQ 文本（异步处理）
curl -X POST http://localhost:8000/v1/knowledge/company-faq/documents \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{
    "title": "退货政策",
    "source_type": "text",
    "content": "客户在收到商品 7 天内可申请退货。退货商品必须保持原包装..."
  }'

# 返回 {task_id, document_id, status: "queued"}
# 轮询任务进度
curl http://localhost:8000/v1/tasks/<task_id> \
  -H "Authorization: Bearer $APP_KEY"
# → {status: "success", progress: 100, result: {chunks: 3}}
```

### Step 2：直接搜（不用 agent，纯 RAG）

```bash
curl -X POST http://localhost:8000/v1/knowledge/company-faq/search \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"query":"怎么退货","top_k":3}'
```

返回 top 3 命中的 chunks。

### Step 3：用 echo agent 做对话（自动 RAG）

echo agent 支持 `doc:<kb_key>` 关键字触发 RAG：

```bash
curl -X POST http://localhost:8000/v1/agents/echo/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{
    "input": "怎么退货 doc:company-faq",
    "stream": false
  }'
```

返回里 `data.citations` 包含命中的 FAQ chunks，你的网站可以渲染"参考依据"块。

### Step 4：写一个真正的 FAQ agent（生产用）

仿照"复杂本地 agent 范式"，写 `chameleon-agents/faq/`：

- `classify` 节点：判断用户问题是否需要 RAG
- `retrieve` 节点：检索 FAQ KB
- `generate` 节点：调真实 LLM 用 citations 生成回答

部署后调用方式不变：`POST /v1/agents/faq/invoke`。

---

## 七、各模块在 Chameleon 项目里的具体位置

| 模块 | 路径 | 干啥 |
|---|---|---|
| **chameleon-core** | `chameleon-core/src/chameleon/core/` | 所有 agent / 业务模块共用的基础设施 |
| ├ config | `core/config/` | 读 .env + JSON 配置，提供 `inventory` 具名 getter |
| ├ logger | `core/logger.py` | loguru 配置 |
| ├ db | `core/db.py` | SQLAlchemy 异步 engine + session |
| ├ auth | `core/auth.py` | API Key 鉴权 |
| ├ response | `core/response.py` | `Result[T]` / `PageResult[T]` |
| ├ exceptions | `core/exceptions.py` | 业务错误码 + 异常家族 |
| ├ models | `core/models/` | 共享 ORM（api_key / conversation / knowledge / task） |
| ├ embedding | `core/embedding/` | embedding 客户端（OpenAI 兼容） |
| ├ vector | `core/vector/` | 向量存储抽象 + pgvector 实现 |
| └ knowledge | `core/knowledge.py` | `search_kb()` in-process API（给 agent 用） |
| **chameleon-providers** | `chameleon-providers/*/` | 三类编排平台的适配器 |
| ├ base | `providers/base/` | Provider 协议 + StreamEvent + registry |
| ├ langgraph | `providers/langgraph/` | 本地 LangGraph in-process provider |
| ├ dify | `providers/dify/` | DIFY HTTP provider |
| └ fastgpt | `providers/fastgpt/` | FastGPT HTTP provider |
| **chameleon-agents** | `chameleon-agents/<key>/` | **你的智能体资产**（一个 agent 一个子包） |
| └ echo | `chameleon-agents/examples/echo_langgraph/` | 范式样板（演示 step/delta/citation） |
| **chameleon-app** | `chameleon-app/src/chameleon/app/` | FastAPI 入口 + 业务模块 |
| ├ main.py | `app/main.py` | FastAPI app + lifespan + 异常 handler |
| ├ cli.py | `app/cli.py` | `chameleon init-admin` 等命令 |
| └ modules/ | `app/modules/` | 业务模块 |
| └ modules/agent | `app/modules/agent/` | `/v1/agents/{key}/invoke` 路由 + 9 步编排 |
| └ modules/conversation | `app/modules/conversation/` | `/v1/conversations/*` 会话管理 |
| └ modules/knowledge | `app/modules/knowledge/` | `/v1/knowledge/*` 知识库 CRUD + ingest |
| └ modules/task | `app/modules/task/` | `/v1/tasks/{id}` 异步任务进度 |
| └ modules/api_key | `app/modules/api_key/` | `/v1/admin/api-keys/*` |
| └ modules/admin | `app/modules/admin/` | `/v1/admin/call-logs` + `/providers/status` |

**关键依赖方向**（铁律，不可破）：

```
chameleon-core
    ↑              ← 谁都依赖它
chameleon-providers-base
    ↑              ← langgraph/dify/fastgpt 都依赖
chameleon-providers/*
    ↑              ← chameleon-app 依赖三个具体 provider
chameleon-app
                   
chameleon-agents/* → chameleon-core（仅！）
                   ← agent 子包是独立资产，可以剥离出去复用
```

---

## 八、何时考虑从 sage 搬东西过来

这些 sage 已有但 Chameleon v1 没有的能力，按需 v0.2 拉过来：

| sage 能力 | 拉过来的工作量 | 何时拉 |
|---|---|---|
| `components/llms/` 多厂商 BaseLLM | 0.5 天（删去 sage db 依赖，改 inventory 读取） | 写第一个真用 LLM 的本地 agent 时 |
| `components/skill/` 技能注册 | 1-2 天 | 第二个 agent 需要复用 skill 时 |
| `BaseAgent` + AgentMetadata | 0.5 天 | 第三个本地 agent 之后，开始觉得 `build_graph` 太散时 |
| `components/cache/` Redis | 0.5 天 | 需要跨请求缓存时 |
| `components/memory/` 会话语义检索 | 1 天 | 需要 message 向量化检索时 |

**搬运原则**：每搬一个先问"我现在真的需要吗"。v1 故意省略——避免在没有真实需求驱动时过度抽象。

---

## 九、最常见的几个问题

**Q: 我有个 LangChain agent（不是 LangGraph），能接入吗？**
A: 可以，但要包一层。LangGraph 是 LangChain 团队推出的图编排库，比 LCEL 更适合复杂 agent。最快路径：把你的 LangChain Runnable 塞到 LangGraph 单节点里：
```python
def build_graph():
    sg = StateGraph(MessagesState)
    sg.add_node("run", lambda s: {"messages": [my_runnable.invoke(s["messages"])]})
    sg.add_edge(START, "run")
    sg.add_edge("run", END)
    return sg.compile()
```

**Q: 我的应用要会话历史，但用户不想让历史落在 Chameleon 这边，怎么办？**
A: 调 invoke 时传 `input: list[Message]` 而不是 `str`——这样 Chameleon 不会从 session 取历史（A10 裁决）。但当前轮 user msg 仍会落库（保证 call_logs 可追溯）。

**Q: 我的 DIFY 应用更新了，怎么让 Chameleon 知道？**
A: DIFY 端的更新（agent 内部逻辑、prompts、知识库）**Chameleon 完全不感知**——它只是个 HTTP 转发。除非你改了 DIFY 应用 ID 或 API key，否则不用动 Chameleon。

**Q: 一个 agent 报错怎么排查？**
A: 三层日志：
1. uvicorn stdout（loguru 格式，含 request_id）
2. `logs/chameleon.log` 文件
3. `GET /v1/admin/call-logs?success=false&agent_key=xxx`（带 admin key）查最近失败调用

**Q: 我要换 LLM 厂商（如 OpenAI 换成 Qwen）怎么做？**
A: 改 `config/model.json` 的 `cases.llm` 字段 + 确保对应 provider 的 `key_env` 在 `.env` 里有值 + 重启。**不动业务代码**。

---

## 十、下一步

1. 跟着"第六节实操"做一遍——把 FAQ agent 跑通
2. 你现在已经有 sage 的 data_qa_v2，可以参考"复杂 agent 范式"章节，把它搬到 `chameleon-agents/data_qa/`
3. 看 `docs/extension-guide.md` —— 8 个扩展场景 step-by-step
4. 出现 v0.2 需求时再从 sage 搬 components

---

## 还是看不懂？

直接告诉我哪里没讲清楚 —— 文档为人服务，不为完整服务。
