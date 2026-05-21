# 扩展指南

Chameleon 设计上有两条**对称的资产积累轴**：

- **Agent 资产**：你的具体智能体（`chameleon-agents/<key>/`）—— **90% 的人只动这里**
- **Provider 资产**：你接入的编排平台（`chameleon-providers/<name>/`）—— **只在加新平台时动**，原理 + 接入 step 全在 [providers.md](providers.md)

加东西的标准动作都很短——下面是 step-by-step。

---

## 1. 加一个本地 agent（**三种范式任选**）

**场景**：你要写一个新智能体，让它走 Chameleon 统一入口对外。

**总耗时**：~10-30 分钟（看选哪种范式 + 业务逻辑复杂度）

★ Chameleon 本地 agent **不锁死编排框架**。三种范式：

| 范式 | 何时用 | 样板 |
|---|---|---|
| **A1. 纯 Python async generator** | 简单逻辑 / 用 Anthropic SDK / 极致灵活 | `chameleon-agents/examples/echo_native/` |
| **A2. LangChain Runnable (LCEL)** | `prompt \| llm \| parser` 链式 | `chameleon-agents/examples/echo_runnable/` |
| **A3. LangGraph CompiledGraph** | 多节点状态机 / 复杂编排 | `chameleon-agents/examples/echo_langgraph/` |

完整三范式代码示例 + 选择指南见 [docs/getting-started.md 第三章 A 节](getting-started.md#a-自己写的本地-agent--三种范式任选)。

下面继续讲共用脚手架：

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
dependencies = [
    "chameleon-core",
    "chameleon-providers-base",
    "langgraph>=0.2",
    # 你需要的额外依赖
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

### Step 3 - 写 `agent.py`（BaseAgent 子类）

`chameleon-agents/my_agent/src/chameleon/agents/my_agent/agent.py`：

```python
from chameleon.core.base import AgentMetadata, BaseAgent


class MyAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="my-agent",                # ★ 唯一 agent key（HTTP path 用）
            name="我的智能体",
            description="干嘛用的一句话",
            version="0.1",
            tags=["domain-x"],
        )

    @classmethod
    def build_graph(cls):
        # 范式 A3：返回 LangGraph CompiledGraph
        ...
    # 或 build_runnable() 返回 LangChain Runnable —— 范式 A2
    # 或 override astream() 直接 yield StreamEvent —— 范式 A1
```

**约定（registry 启动自动扫描）**：
- 模块顶层必须有一个 `BaseAgent` 子类
- 子类必须实现 `get_metadata()` —— `id` 即对外 agent_key
- 三选一实现：`astream()` / `build_graph()` / `build_runnable()`

### Step 4 - export 子类

`chameleon-agents/my_agent/src/chameleon/agents/my_agent/__init__.py`：

```python
from chameleon.agents.my_agent.agent import MyAgent
__all__ = ["MyAgent"]
```

参考完整实现：
- LangGraph 范式：`chameleon-agents/examples/echo_langgraph/`
- Runnable 范式：`chameleon-agents/examples/echo_runnable/`
- 纯 Python：`chameleon-agents/examples/echo_native/`
- 真实业务（用全局 LLM）：`chameleon-agents/qwen_chat/`

### Step 5 - RAG（可选）

```python
from chameleon.core.components import search_kb

async def lookup_node(state):
    hits = await search_kb("my-kb", query, top_k=5, min_score=0.3)
    citations = [
        {"source": f"chunk:{h.id}", "score": h.score, "snippet": h.content[:200]}
        for h in hits
    ]
    return {"citations": citations}   # citations 字段在 state 里
```

返回 state 的 `citations` 字段会被 langgraph_bridge 翻译层自动 emit 为 citation event。

### Step 6 - 装 + 重启

```bash
uv sync --all-packages           # 装新子包
uv run uvicorn chameleon.app.main:app --reload
```

启动日志应该出现：

```
agent registered (local) | key=my-agent | class=MyAgent | module=chameleon.agents.my_agent
```

### Step 7 - 调

```bash
curl -X POST http://localhost:8000/v1/agents/my-agent/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input":"hi","stream":true}'
```

### 业务 agent vs 示例 agent 怎么分

- 业务 agent（你真正用的）→ 放 `chameleon-agents/<key>/` 根目录
- 示例 / 范式样板（教学性质）→ 放 `chameleon-agents/examples/<key>/`

两者技术上完全一样，只是组织清晰度的约定。registry 扫 `chameleon.agents.*` namespace 时两层都扫得到。

### 依赖约束（铁律）

```
chameleon-agents/<x>  →  chameleon-core    （仅！）
```

**agent 子包只能依赖 chameleon-core**。这保证你的 AI 资产可独立迁移。
RAG 通过 `chameleon.core.components.search_kb` 访问，知识库 ORM 不暴露。

---

## 2. 加一个外部 DIFY agent

**场景**：你在 DIFY 平台编排好了一个 agent，想让 Chameleon 接入。

**总耗时**：~5 分钟（纯配置）

> DIFY agent 怎么被调用 / SSE 怎么翻译 / 错误怎么映射 → 见 [providers.md](providers.md) 的 "DifyProvider" 节

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

### Step 2 - 在 `config/.env` 加 key

```env
DIFY_FAQ_KEY=app-xxxxxxxxxxxxxx
DIFY_FAQ_APP_ID=abcdef-1234       # 仅当你的 yaml 引用 ${env:DIFY_FAQ_APP_ID}
```

### Step 3 - 重启

```bash
# 重启服务
uvicorn chameleon.app.main:app
```

启动日志应该出现：

```
agent registered (yaml) | key=customer-faq | provider=dify
```

### Step 4 - 调（与本地 agent 用法一致）

```bash
curl -X POST http://localhost:8000/v1/agents/customer-faq/invoke \
  -H "Authorization: Bearer $APP_KEY" \
  -d '{"input":"如何退货","stream":true}'
```

DIFY 的 `conversation_id` 会被 Chameleon 自动双写到 `conversations.provider_conv_id`——下次带 `session_id` 调用时透传给 DIFY，DIFY 端会话状态延续。

---

## 3. 加一个外部 FastGPT agent

形态与 DIFY 完全对称。原理见 [providers.md](providers.md) 的 "FastGPTProvider" 节。

```yaml

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

FastGPT 的 `chatId` 同样被双写。

---

## 4. 加一类全新 provider（如 Coze、n8n、自研编排）

整章 step-by-step 已搬到 [providers.md](providers.md) 的 "如何加一个新 Provider" 节。

该文档还讲了 Provider 抽象层的整体原理 / 调用链 / 三个内置 provider 的内部实现，加新 provider 前建议先读一遍。

---

## 5. 加一个 vector store（如 Milvus、Qdrant、Chroma）

**场景**：v1 默认 pgvector；你想切到 Milvus 之类的专业向量数据库。

### Step 1 - 实现 VectorStore Protocol

`chameleon-core/src/chameleon/core/vector/milvus.py`：

```python
from chameleon.core.vector.base import ChunkPayload, ChunkHit, VectorStore


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

`chameleon-core/src/chameleon/core/vector/factory.py` 加：

```python
elif backend == "milvus":
    _STORE = MilvusStore()
```

### Step 3 - 配置切换

在 `chameleon.json` 里加：

```json
{
  "vector": {
    "backend": "milvus"
  }
}
```

并在 `inventory.py` 加 getter（v1 没暴露 `vector_backend()`，可加）：

```python
def vector_backend() -> str:
    return chameleon_settings.get("vector.backend") or "pgvector"
```

### Step 4 - 重启

向量存储是单例，启动时实例化一次。

---

## 6. 加一种 LLM provider（embedding / chat）

v1 默认 OpenAI 兼容协议（OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 同走）。

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

`.env`：

```env
MOONSHOT_API_KEY=ms-xxx
```

完事——不需要写代码。

**非 OpenAI 兼容协议的厂商**：要写一个 `EmbeddingClient` 实现（参考 `core/embedding/openai_compat.py`），在 factory 里加分支。

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
- 对外：`chameleon-api/.../conversation/`、`chameleon-api/.../knowledge/`
- 对内：`chameleon-system/.../api_key/`、`chameleon-system/.../admin/`

### Step 3 - 挂到 main.py

```python
# chameleon-app/src/chameleon/app/main.py
from chameleon.app.modules.my_module import router as my_module_router

def _mount_routers(app: FastAPI) -> None:
    ...
    app.include_router(my_module_router)
```

### 规约红线（必守）

来自 `~/.claude/rules/python-codebase.md`：

- ❌ API 层写 SQL / 不直接调 Mapper
- ❌ Service 返 ORM 给 API（必须转 schemas DTO）
- ❌ 不包统一 `Result[T]` 直接返裸数据
- ❌ try/except 在 API 层吃异常（交给全局 handler）
- ✅ 所有 `BusinessError` 子类 raise 出去，全局 handler 接管
- ✅ loguru `{}` 占位符，禁止字符串拼接日志
- ✅ 类型注解齐全

---

## 8. 加新错误码

`chameleon-core/src/chameleon/core/api/exceptions.py` 加 enum 成员：

```python
class ResultCode(IntEnum):
    ...
    KbQuotaExceeded = 42910    # 新加，自定义段位
```

加对应 message：

```python
_CODE_MESSAGES = {
    ...
    ResultCode.KbQuotaExceeded: "知识库配额超限",
}
```

派生 BusinessError 子类（可选）：

```python
class KbQuotaExceededError(BusinessError):
    code = ResultCode.KbQuotaExceeded
```

HTTP status 推断：`code_to_http_status` 自动按段位映射（42910 → 429）。

---

## 8 张快查表

| 扩展点 | 入口 | 改动半径 |
|---|---|---|
| 新本地 agent | `chameleon-agents/<key>/` | 仅新子包 |
| 新外部 agent | `config/agents.yaml` + `.env` | 仅配置 |
| 新 provider | `chameleon-providers/<name>/` | 仅新子包 |
| 新 vector store | `core/vector/<name>.py` + factory | 单文件 |
| 新 LLM 厂商（兼容） | `baseurl.json` + `model.json` + `.env` | 仅配置 |
| 新业务模块 | `chameleon-api/.../<name>/` 或 `chameleon-system/.../<name>/` + main.py 挂载 | 按"对外/对内"选包 |
| 新错误码 | `core/api/exceptions.py` 加 enum | 单文件 |
| 新 StreamEvent 类型 | `providers/base/types.py` + 所有 provider 同步 | 横切 |
