# Provider 适配层

> **写本地 agent 不需要看这篇**。这是讲 Chameleon 内部"agent 怎么被执行"的抽象层。
> 只在以下两种场景才会看：（1）想接入 DIFY / FastGPT 之外的新平台；（2）排查跨平台事件流问题。

---

## 一句话定义

Provider 是 Chameleon 内部把**多种 agent 调用方式**统一到**一种事件流协议**的抽象层。

- **它是什么**：一组实现 `Provider` 协议的子包，每种 agent 来源一个（`local` / `dify` / `fastgpt`）
- **它干什么**：把"业务方一个 HTTP 调用"翻译成具体平台的执行（本地 import + astream / DIFY HTTP / FastGPT HTTP），再把各平台原生事件流翻成 Chameleon `StreamEvent`
- **它不是什么**：不是业务逻辑，不是 agent 本身，不是路由网关

---

## 它解决什么问题

没有 Provider 层，Chameleon 的 API 入口要写成这样：

```python
@router.post("/v1/agents/{key}/invoke")
async def invoke(key: str, ...):
    agent = AGENTS[key]
    if agent.source == "local":
        cls = importlib.import_module(...).get_class()
        async for ev in cls.astream(ctx):
            yield translate_local(ev)
    elif agent.source == "dify":
        async with httpx.stream(...) as r:
            async for line in r.aiter_lines():
                yield translate_dify_sse(line)
    elif agent.source == "fastgpt":
        # 又是另一套
        ...
    # 每加一个平台，这里 if 分支多一段
    # 每个平台的错误码、超时、鉴权都要单独 catch
```

这有 4 个明显问题：
1. **业务方耦合到具体平台**：API 入口知道 dify 的 SSE 格式
2. **每加一个平台 N+1 处改动**：错误处理、超时配置、事件翻译都要复制
3. **测试地狱**：mock 一个 dify 要 mock httpx，mock 本地要 mock importlib
4. **错误码各异**：DIFY 401、FastGPT `code: 10001`、本地 `BusinessError`，业务层处理不过来

Provider 层把这些**封装在子包里**，API 入口只剩：

```python
@router.post("/v1/agents/{key}/invoke")
async def invoke(key: str, ...):
    agent = AGENTS[key]
    provider = PROVIDERS[agent.provider]  # ← 选哪个 provider
    async for ev in provider.stream(ctx):  # ← 已经是 StreamEvent
        yield ev
```

业务方调 API 完全感觉不到 agent 跑在哪里。

---

## 三个核心职责

### 1. 路由分发

启动时 `init_registry()` 扫描两个 namespace：

- `chameleon.providers.*` → 收 `PROVIDER` export，建 `PROVIDERS: dict[str, Provider]`
- `chameleon.agents.*` + `config/agents.yaml` → 建 `AGENTS: dict[str, AgentDef]`

每个 `AgentDef` 里有 `provider: str` 字段，运行时按这个字段从 `PROVIDERS` 取实例。

#### AgentDef：agent 的"身份证"

`AgentDef`（定义在 `chameleon-providers/base/.../types.py`）是注册表里每个 agent 的不可变描述对象。Provider 拿到它就有了"调用这个 agent 所需的全部信息"。

```python
class AgentDef(BaseModel):
    key: str                      # 对外 agent_key（API 路径里那一段）
    provider: str                 # 选哪个 Provider 执行（"local" / "dify" / "fastgpt" / ...）
    description: str = ""         # 人类可读说明
    version: str | None = None
    tags: list[str] = []          # 标签（用于分组 / 过滤）
    config: dict[str, Any] = {}   # provider-specific 配置（见下表）

    model_config = ConfigDict(frozen=True)   # 启动后只读，运行时不可变
```

**关键字段说明**：

| 字段 | 作用 | 谁填 |
|---|---|---|
| `key` | 对外 agent 标识，业务方 POST `/v1/agents/{key}/invoke` 时用 | 本地 agent：`get_metadata().id`；yaml agent：`agents.yaml` 里 `key:` |
| `provider` | 路由分发的依据，决定用哪个 Provider 执行 | 本地 agent：固定 `"local"`；yaml agent：yaml 里 `provider:` |
| `config` | provider 读取的配置参数，**结构 provider-specific** | 同 provider |
| `frozen=True` | 启动后整个对象不可变，避免运行时被改 | pydantic 强制 |

**`config` 字段的 provider-specific 结构**：

| provider | config 字段 | 谁生成 |
|---|---|---|
| `local` | `{"module": "chameleon.agents.qwen_chat", "agent_class": "QwenChatAgent"}` | registry 扫描 BaseAgent 子类时自动填 |
| `dify` | `{"endpoint": "https://api.dify.ai/v1", "app_id": "...", "api_key_env": "DIFY_KEY", "mode": "chat"}` | `agents.yaml` 用户填 |
| `fastgpt` | `{"endpoint": "...", "app_id": "...", "api_key_env": "FASTGPT_KEY"}` | `agents.yaml` 用户填 |

Provider 内部从 `ctx.agent_def.config` 取这些字段。**Provider 不该假定 `config` 里有什么**，必须显式校验缺失字段 → raise `ProviderConfigError`。

**AgentDef 怎么进到调用链**：

```
启动期：
  扫描 chameleon.agents.* → 每个 BaseAgent 子类生成 AgentDef(provider="local", config={module, agent_class})
  读 config/agents.yaml   → 每条 entry 生成 AgentDef(provider=<yaml.provider>, config=<剩余字段>)
  合并 → AGENTS: dict[str, AgentDef]

调用期：
  POST /v1/agents/{key}/invoke
    → agent_def = AGENTS[key]
    → provider = PROVIDERS[agent_def.provider]
    → ctx = InvokeContext(agent_def=agent_def, input=..., ...)
    → async for ev in provider.stream(ctx): ...
```

### 2. 协议翻译

各平台的原生事件流截然不同：

| 平台 | 原生事件 |
|---|---|
| LangGraph CompiledGraph | `astream_events()` 产出 `on_chat_model_stream` / `on_chain_end` / `on_tool_start` 等 LangChain runnable 事件 |
| LangChain Runnable | `astream()` 产出 `AIMessageChunk` |
| 纯 Python async generator | 用户自己 yield 什么都行（约定 yield `StreamEvent`） |
| DIFY API | SSE 流：`event: message` / `event: workflow_finished` / `event: error` 等 |
| FastGPT API | SSE 流：OpenAI 兼容 `data: {choices: [{delta: ...}]}` + 自定义 `event` |

Provider 翻译为统一 8 种事件（封闭枚举）：

```
delta | step | citation | tool_call | tool_result | metadata | done | error
```

不在这 8 种里的概念塞 `metadata` 或 `step.thinking` 字段。

### 3. 错误归一化

每个平台的错误形态都不同（HTTP 401 vs JSON `{code: 10001}` vs Python `RuntimeError`），Provider 内部 catch 后统一抛 `ProviderError` 家族：

```python
from chameleon.providers.base.errors import (
    ProviderUnreachableError,    # 网络 / 超时
    ProviderAuthError,           # 401 / 403
    ProviderRateLimitError,      # 429
    ProviderInputError,          # 4xx 业务错误
    ProviderInternalError,       # 5xx 兜底
    ProviderConfigError,         # 配置缺失（启动期）
)
```

全局异常 handler 拦到这些异常 → 翻成 `Result.fail(code, message)` 响应，业务层不写一行 try/except。

---

## 端到端调用链路

```
你的应用
  │
  │ POST /v1/agents/customer-faq/invoke
  │ Authorization: Bearer <app_key>
  │ {"input": "...", "stream": true}
  ↓
─────────────────────────────────────────────────
chameleon-app/.../api/agent.py
  │ ① auth：校验 app_key（middleware）
  │ ② 取 AgentDef：AGENTS["customer-faq"]
  │    → AgentDef(key="customer-faq", provider="dify", config={...})
  │ ③ 取 Provider：PROVIDERS["dify"]
  │    → DifyProvider 实例
  │ ④ 装配 InvokeContext：
  │    InvokeContext(
  │       agent_def, input, history, session_id,
  │       provider_conv_id, app_id, stream=True, ...
  │    )
  ↓
─────────────────────────────────────────────────
DifyProvider.stream(ctx)         （在 chameleon-providers/dify/）
  │
  │ a. 构造 DIFY 请求体（history → DIFY conversation_id 续会话）
  │ b. httpx.AsyncClient.stream() 发起 SSE 调用
  │ c. 异常 catch：
  │     - httpx.TimeoutException → ProviderUnreachableError
  │     - 401  → ProviderAuthError
  │     - 429  → ProviderRateLimitError
  │     - 5xx  → ProviderInternalError
  │ d. 逐行解析 SSE：
  │     event: message      → StreamEvent(type=delta,   data={text: ...})
  │     event: workflow_step → StreamEvent(type=step,    data={...})
  │     event: workflow_finished → StreamEvent(type=done, data={...})
  │     event: error         → StreamEvent(type=error,   data={...})
  ↓
StreamEvent 流（async generator）
  ↓
─────────────────────────────────────────────────
chameleon-app/.../api/agent.py
  │ ⑤ stream=True → 包成 SSE 响应回写
  │ ⑥ 同步双写 conversations/messages 表（持久化）
  │ ⑦ provider_conv_id → conversations.provider_conv_id
  ↓
HTTP 响应（text/event-stream）
  ↓
你的应用收到统一的 SSE 流
```

**关键**：业务方看到的事件格式恒定，不管 agent 是本地 / DIFY / FastGPT。

---

## 接口契约

### Provider 协议（`providers/base/protocol.py`）

```python
class Provider(ABC):
    name: str                                         # 子类必须设置

    @abstractmethod
    def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """流式调用 —— 必须实现"""

    async def invoke(self, ctx: InvokeContext) -> InvokeResult:
        """非流式：默认聚合 stream()；有原生非流模式可 override"""

    async def healthcheck(self) -> bool:
        """启动 / 定时 ping。warn-only，默认返 True"""
```

**最小要求**：子类只需实现 `stream()`。`invoke()` 用 `_StreamAggregator` 自动聚合事件得到 `InvokeResult`。

### StreamEvent（`providers/base/types.py`）

```python
class StreamEventType(StrEnum):
    delta = "delta"           # 增量 token（answer chunk）
    step = "step"             # 中间步骤（节点完成 / 子流程切换）
    citation = "citation"     # 知识引用
    tool_call = "tool_call"   # 工具调用记录（不含结果）
    tool_result = "tool_result"  # 工具结果
    metadata = "metadata"     # 元数据（usage / provider_conv_id 等）
    done = "done"             # 完成事件（data = InvokeResult.model_dump()）
    error = "error"           # 流中错误（业务异常 / 平台错误）

class StreamEvent(BaseModel):
    type: StreamEventType
    data: dict[str, Any]
```

### InvokeContext

每次调用打包好的上下文：

```python
class InvokeContext(BaseModel):
    agent_def: AgentDef
    input: str | list[Message]
    history: list[Message]
    session_id: str                  # Chameleon 自己的 session
    provider_conv_id: str | None     # 平台端会话 ID（双写续会话用）
    context_vars: dict               # 业务层透传变量
    options: dict                    # 调用选项（temperature 等）
    app_id: str                      # 调用方应用 ID
    stream: bool
    request_id: str | None
```

### `_StreamAggregator`

`invoke()` 默认实现用它把 `stream()` 的事件聚合成 `InvokeResult`：

- `delta` → 累加到 `answer`
- `step` → 追加到 `steps[]`
- `citation` → 追加到 `citations[]`
- `tool_call` + `tool_result` → 合并到 `tool_calls[]`（按 name 配对）
- `metadata.usage` → 设到 `usage`
- `done.data` → 直接覆盖累积值（done 是终态）

这意味着 provider 写起来最大灵活度：

- DIFY：答案靠 `delta` 累积，done 不带 answer 也行
- LangGraph：`chain_end` 才知道完整答案，done 带 answer 覆盖累积
- FastGPT：类似 DIFY

---

## 三个内置 Provider 原理

### LocalProvider（`providers/local/`）

**用途**：调本地 in-process agent（你写的 BaseAgent 子类），零网络 IO，毫秒级。

**核心代码**：

```python
class LocalProvider(Provider):
    name = "local"

    async def stream(self, ctx):
        cfg = ctx.agent_def.config
        mod = importlib.import_module(cfg["module"])
        agent_cls = getattr(mod, cfg["agent_class"])
        async for ev in agent_cls.astream(ctx):
            yield ev
```

**它不关心 agent 内部用什么范式**——LangGraph / LangChain Runnable / 纯 Python yield 都行，事件流统一由 `BaseAgent.astream()` 产出。

**agent → StreamEvent 翻译在哪做？** 在 `BaseAgent` 提供的桥（bridges）里：

- LangGraph CompiledGraph：`chameleon.core.base.bridges.langgraph_bridge.astream_from_langgraph_graph()`
- LangChain Runnable：`chameleon.core.base.bridges.langchain_bridge.astream_from_runnable()`

agent 作者写一个 classmethod 即可：

```python
class MyAgent(BaseAgent):
    @classmethod
    def build_graph(cls):  # LangGraph 范式
        return ...
    # 或：
    @classmethod
    def build_runnable(cls):  # LangChain 范式
        return prompt | llm
    # 或：
    @classmethod
    async def astream(cls, ctx):  # 纯 Python 范式
        yield StreamEvent(type=delta, data={"text": "..."})
```

`BaseAgent.astream()` 默认实现会按优先级（自定义 astream > build_graph > build_runnable）选桥调用。

### DifyProvider（`providers/dify/`）

**用途**：HTTP 远调 DIFY 平台上的 chatflow / workflow / agent。

**子包结构**：
```
dify/
  __init__.py     ← export PROVIDER = DifyProvider()
  provider.py     ← class DifyProvider(Provider)，调度 client + stream
  client.py       ← httpx.AsyncClient 封装（鉴权 / 重试 / 超时）
  stream.py       ← DIFY SSE → StreamEvent 翻译器
```

**DIFY SSE 事件映射**：

| DIFY 事件 | Chameleon StreamEvent |
|---|---|
| `event: message` | `delta(text=answer chunk)` |
| `event: workflow_started` / `node_started` | `step(name=..., status=running)` |
| `event: node_finished` | `step(name=..., status=success, output=...)` |
| `event: agent_thought` | `step(thinking=...)` |
| `event: message_end` | `metadata(usage=..., provider_conv_id=...)` |
| `event: workflow_finished` | `done(data=...)` |
| `event: error` | `error(code=..., message=...)` |

**续会话**：DIFY 的 `conversation_id` 双写到 `conversations.provider_conv_id`，下次同 session_id 调用时透传。

### FastGPTProvider（`providers/fastgpt/`）

**用途**：HTTP 远调 FastGPT 平台。FastGPT 走 OpenAI 兼容 API。

**子包结构**：与 DIFY 对称（`provider.py` / `client.py` / `stream.py`）。

**FastGPT 流事件**：FastGPT 用 OpenAI 兼容 `data: {choices: [{delta: {content: ...}}]}` + 自定义 `event: flowNodeStatus` / `event: flowResponses`。

**关键映射**：
- `data: choices[].delta.content` → `delta`
- `event: flowNodeStatus` → `step`
- `event: flowResponses` → `step + metadata`（带 token usage / citations）

---

## 注册机制

启动入口 `chameleon-app/.../main.py` 调用 `init_registry()`：

```python
from chameleon.providers.base.registry import init_registry, PROVIDERS, AGENTS

def create_app():
    init_registry()
    # 此时 PROVIDERS, AGENTS 已建好，运行时只读
```

### Provider 扫描

```python
def build_provider_registry() -> dict[str, Provider]:
    import chameleon.providers as pkg
    providers = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__, "chameleon.providers."):
        if mod_info.name.endswith(".base"):
            continue                                  # base 子包跳过
        mod = importlib.import_module(mod_info.name)
        provider = getattr(mod, "PROVIDER", None)     # ★ 约定符号
        if provider is None:
            continue
        providers[provider.name] = provider
    return providers
```

约定：

- 子包路径：`chameleon-providers/<name>/src/chameleon/providers/<name>/`
- `__init__.py` 必须 export `PROVIDER = <YourProvider>()`
- `PROVIDER.name` 必须唯一（重复直接 RegistryError 启动失败）

### Agent 扫描

双源合并：

1. **本地 namespace**：扫 `chameleon.agents.*`，找每个子模块的 `BaseAgent` 子类 → `AgentDef(provider="local", ...)`
2. **yaml**：读 `config/agents.yaml`，每条 entry 按 `provider` 字段建 `AgentDef`

合并时 key 冲突直接 RegistryError；引用的 provider 不在 `PROVIDERS` 里也 RegistryError。**fail-fast 启动**。

---

## 错误归一化

### ProviderError 家族

```
ProviderError              ← 基类（业务异常体系的一员）
├── ProviderConfigError    ← 配置缺失（启动 / 调用前置）
├── ProviderUnreachableError  ← 网络 / 超时
├── ProviderAuthError      ← 401 / 403
├── ProviderInputError     ← 4xx 业务错误（参数 / 流程不合法）
├── ProviderRateLimitError ← 429
└── ProviderInternalError  ← 5xx 平台兜底
```

### 翻译路径

```
DIFY HTTP 401         → ProviderAuthError      → Result(code=4011, msg="平台鉴权失败")
FastGPT HTTP timeout  → ProviderUnreachableError → Result(code=5031, msg="平台不可达")
LangGraph 内部 Exception → ProviderInternalError  → Result(code=5009, msg="agent 执行失败")
```

具体 code 在 `chameleon.core.api.exceptions.ResultCode` 枚举。全局 handler 在 `chameleon-app/.../main.py` 统一兜，**业务层不处理这些异常**。

### error event vs 异常

Provider 内部分两种"出错路径"：

- **致命错误**（连不上、鉴权失败、配置缺失）→ raise `ProviderError`，stream 中断
- **流中可恢复错误**（DIFY workflow 内部节点失败但流程继续）→ yield `StreamEvent(type=error, data={...})`，stream 不中断

业务方在 SSE 流里看到 `event: error` 表示"这次执行有问题但已结束"；看到 HTTP 5xx 才是"Provider 自己挂了"。

---

## 如何加一个新 Provider（接入 Coze / n8n / 自研编排）

**场景**：你想接入 Chameleon 还没支持的编排平台。

**总耗时**：~1-2 天（含适配 + 单测）

### Step 1 - 建子包

```bash
mkdir -p chameleon-providers/coze/src/chameleon/providers/coze
mkdir -p chameleon-providers/coze/tests
```

### Step 2 - `pyproject.toml`

```toml
[project]
name = "chameleon-provider-coze"
version = "0.1.0"
description = "Chameleon Coze provider"
requires-python = ">=3.12"
dependencies = [
    "chameleon-core",
    "chameleon-providers-base",
    "httpx>=0.27",
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

### Step 3 - 实现 Provider 协议

`provider.py`：

```python
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext, StreamEvent, StreamEventType,
)


class CozeProvider(Provider):
    name = "coze"

    async def stream(self, ctx: InvokeContext):
        # 1. 从 ctx.agent_def.config 取 endpoint / api_key_env
        # 2. 翻译 ctx.history + ctx.input → Coze 入参格式
        # 3. 调 Coze HTTP API（流式或非流）
        # 4. 把 Coze 事件翻成 StreamEvent 并 yield
        yield StreamEvent(type=StreamEventType.delta, data={"text": "..."})
```

**最小要求**：只实现 `stream()` 即可。

### Step 4 - export PROVIDER 实例

`__init__.py`：

```python
from chameleon.providers.coze.provider import CozeProvider

PROVIDER = CozeProvider()                  # ★ registry 扫这个符号

__all__ = ["PROVIDER", "CozeProvider"]
```

### Step 5 - 错误映射

provider 内部 catch 原生异常 → raise `chameleon.providers.base.errors` 里的对应错误：

```python
from chameleon.providers.base.errors import (
    ProviderUnreachableError, ProviderAuthError,
    ProviderRateLimitError, ProviderInputError, ProviderInternalError,
)

try:
    resp = await client.post(...)
except httpx.TimeoutException as e:
    raise ProviderUnreachableError(message=str(e)) from e
```

### Step 6 - 流式翻译

参考 `chameleon-providers/dify/src/chameleon/providers/dify/stream.py`：把 Coze 的事件流翻成 StreamEvent。8 种事件类型见上文。

### Step 7 - 装 + 重启

```bash
uv sync --all-packages
uvicorn chameleon.app.main:app
```

启动日志应包含：

```
provider registered | name=coze | from=chameleon.providers.coze
```

### Step 8 - 加 agent 配置

```yaml
# config/agents.yaml
- key: my-coze-agent
  provider: coze
  endpoint: https://api.coze.cn/v1
  api_key_env: COZE_KEY
  # provider-specific config 字段...
```

---

## FAQ

**Q：我只写本地 agent，要写 provider 吗？**
A：不用。`LocalProvider` 已经写好了，自动 import 你的 BaseAgent 子类调 `astream()`。

**Q：能给同一个 agent 切 provider 吗（比如先 DIFY 调通再迁本地）？**
A：能。改 `config/agents.yaml` 里 `provider:` 字段即可，业务方 API key + agent_key 不变。

**Q：Provider 是不是有点像 LangChain 的 LLM provider？**
A：思路相同（抽象多家厂商到统一接口），但层级不同。LangChain 的 provider 是抽象**单个 LLM**；Chameleon 的 Provider 抽象的是**完整的 agent 执行单元**（含编排 / 检索 / 工具调用 / 多轮上下文）。

**Q：能不能不用 SSE，统一走 WebSocket？**
A：架构允许。`Provider.stream()` 产出的是 async generator，外层包成 SSE 还是 WS 由 API 入口决定。当前 v0.1 选 SSE 是因为业务方更普及。

**Q：DifyProvider 内部用 httpx，能换成 aiohttp 吗？**
A：能。Provider 内部技术栈完全自由，只要满足 `Provider` ABC 协议。

**Q：怎么排查"Provider 选错了"的问题？**
A：启动日志 `agent registered ... | provider=xxx` 表明 agent 绑定了哪个 provider；调用日志 `local provider | agent=xxx` 表明运行时选了哪个 provider。两个对不上说明 yaml 或 namespace 扫描出问题。

**Q：Provider healthcheck 失败会怎样？**
A：启动期 warn-only，不阻塞。调用时如果 provider 内部连不上会抛 `ProviderUnreachableError`，业务方收到 `Result.fail(code=5031, ...)`。

---

## 相关文件索引

| 路径 | 说明 |
|---|---|
| `chameleon-providers/base/src/chameleon/providers/base/protocol.py` | `Provider` ABC |
| `chameleon-providers/base/src/chameleon/providers/base/types.py` | StreamEvent / AgentDef / InvokeContext / `_StreamAggregator` |
| `chameleon-providers/base/src/chameleon/providers/base/errors.py` | `ProviderError` 家族 re-export |
| `chameleon-providers/base/src/chameleon/providers/base/registry.py` | namespace 扫描 + 双源合并 |
| `chameleon-providers/local/.../provider.py` | LocalProvider 实现 |
| `chameleon-providers/dify/.../{provider,client,stream}.py` | DifyProvider 三件套 |
| `chameleon-providers/fastgpt/.../{provider,client,stream}.py` | FastGPTProvider 三件套 |
| `chameleon-core/src/chameleon/core/base/bridges/langgraph_bridge.py` | LangGraph CompiledGraph → StreamEvent 翻译桥 |
| `chameleon-core/src/chameleon/core/base/bridges/langchain_bridge.py` | LangChain Runnable → StreamEvent 翻译桥 |
| `chameleon-core/src/chameleon/core/api/exceptions.py` | `ProviderError` 家族定义 + `ResultCode` 枚举 |
