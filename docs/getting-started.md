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

---

## 二、项目模块大白话对照

如果你以前看 sage，下面这表帮你快速建立映射：

| sage 里的概念 | Chameleon 里的位置 | 干嘛的 |
|---|---|---|
| `sage-core/components/llms/` | `chameleon-core/.../core/embedding/openai_compat.py`（同样思路，目前仅 embedding；LLM 待 v0.2 补） | LLM / embedding 客户端工厂 |
| `sage-core/components/vector/` | `chameleon-core/.../core/vector/` | 向量存储抽象 + pgvector 实现 |
| `sage-core/components/inventory.py` | `chameleon-core/.../core/config/inventory.py` + `chameleon.core.knowledge.search_kb` | 全局访问点（配置 + 知识库 in-process API） |
| `sage-core/components/skill/` | （v1 暂无；future v0.2 看需求） | 技能注册 / lazy reference |
| `sage-core/components/cache/` | （v1 暂无） | 缓存 |
| `sage-core/base/base_agent.py` | （v1 暂无 BaseAgent 基类；本地 agent 直接写 `build_graph`） | agent 基类 |
| `sage-agents/data_qa_v2/agent.py` | `chameleon-agents/<your_agent>/` 子包 | 具体 agent 实现 |
| `sage-agents/data_qa_v2/deps_factory.py` | （范式参考，没强制） | 依赖注入工厂 |
| `sage-agents/data_qa_v2/function/graph/` | 你 agent 子包里的 `graph.py` + `nodes/` 目录 | LangGraph 图与节点 |
| `sage-system/modules/chat/` | `chameleon-app/.../modules/agent/` | HTTP 入口 + 会话编排 |

**实话实说**：v1 的 Chameleon 在 LLM 接入、技能系统、复杂 deps 注入这些方面**没有 sage 成熟**。v1 优先打通"三类来源统一入口"的骨架，components 的丰富度让位给后续迭代。你想用 sage 那套 LLM 多厂商，可以参考"把 sage components 搬过来"的 v0.2 思路（见末尾）。

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

### A. 自己写的本地 LangGraph agent

**最少 5 分钟，最简版**（参考已实现的 `chameleon-agents/echo/`）：

```bash
# 1. 建子包
mkdir -p chameleon-agents/my_agent/src/chameleon/agents/my_agent

# 2. pyproject.toml（5 行模板，照抄 echo 改名）
cat > chameleon-agents/my_agent/pyproject.toml <<EOF
[project]
name = "chameleon-agent-my-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "chameleon-core",
    "chameleon-providers-base",
    "langgraph>=0.2",
]

[tool.uv.sources]
chameleon-core = { workspace = true }
chameleon-providers-base = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/chameleon"]
EOF
```

**关键：注册接口**——`__init__.py` 必须有两样：

```python
# chameleon-agents/my_agent/src/chameleon/agents/my_agent/__init__.py
from .graph import build_graph

AGENT_META = {
    "key": "my-agent",            # 外部应用通过这个 key 调用：POST /v1/agents/my-agent/invoke
    "description": "干啥的一句话",
    "version": "0.1",
    "tags": ["domain"],
}
```

然后 `graph.py` 是真正的智能体逻辑（一个 LangGraph CompiledGraph）。

```bash
# 3. 装并启动
uv sync --all-packages
uv run uvicorn chameleon.app.main:app
```

启动日志会自动出现：
```
agent registered (local langgraph) | key=my-agent | module=chameleon.agents.my_agent
```

**外部应用立刻能调**：

```bash
curl -X POST http://localhost:8000/v1/agents/my-agent/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input": "嗨", "stream": true}'
```

➡️ **复杂 agent 怎么写？** 看下面"sage 风格范式"章节。

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
| └ echo | `chameleon-agents/echo/` | 范式样板（演示 step/delta/citation） |
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
