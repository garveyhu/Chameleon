# chameleon-agentkit

Chameleon 编码智能体作者 SDK。**只写业务逻辑**——模型、知识库、工具、追踪、记忆、子智能体、多模态都从一个绑定了「本 agent 配置 + 本次请求」的运行时 `ctx` 隐式拿到。同一份 `handle` 代码，换 transport 即换运行环境：本机脱平台跑 → 连 dev 服务自测 → 提交进 `chameleon-agents/` 站内运行，零改动。

## 30 秒 quickstart（脱平台）

> ⚠️ 尚未发布到 PyPI。当前请从仓库 workspace 本地装：`cd backend && uv sync`（或
> `pip install -e chameleon-agentkit`）。下方 `pip install chameleon-agentkit` 是发布后的目标用法。

只装 SDK + 自带模型 key，不连任何站点：

```python
import asyncio
from chameleon.agentkit import agent, AgentRun, ModelSlot
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone
from langchain_openai import ChatOpenAI

@agent(key="hello", name="助手", models=[ModelSlot("chat", "对话")])
async def handle(ctx: AgentRun):
    async for delta in ctx.stream(system="你是助手", user=ctx.query):
        yield delta

t = StandaloneTransport(model=ChatOpenAI(model="gpt-4o-mini"))  # 你自己的 key
print(asyncio.run(run_standalone(handle, "用一句话介绍你自己", transport=t)))
```

```bash
pip install chameleon-agentkit langchain-openai
python hello.py
```

`StandaloneTransport` 下：模型走你传入的 LangChain model，记忆/知识库/工具循环/子智能体全本地，
多模态等平台专属能力显式报错。脱平台与平台的行为差异见 `docs/agentkit-guide.md`「完全脱平台跑」。

## 离线单测（确定性，无需模型）

```python
from chameleon.agentkit.testing import FakeTransport, make_run, collect

async def test_hi():
    run = make_run(handle, query="hi", transport=FakeTransport(replies=["你好"]))
    assert "你好" in await collect(handle(run))
```

## 5 分钟 quickstart（连 dev 服务 / 提交注册）

### 1. 写一个带工具的 agent

```python
# my_agent.py
from chameleon.agentkit import agent, tool, AgentRun, ModelSlot, Opt

@tool(name="calc", description="计算一个算术表达式")
async def calc(expression: str) -> dict:
    return {"value": eval(expression, {"__builtins__": {}}, {})}  # 示例，生产请做安全校验

@agent(
    key="my-assistant", name="我的助手",
    models=[ModelSlot("chat", "对话模型")],   # web「关联模型」可绑/切，留空走系统默认
    tools=["http"],                            # 平台工具点名，web「关联工具」可启停
    config=[Opt("max_steps", "工具循环上限", type="number", default=6)],
)
async def handle(ctx: AgentRun):
    async for delta in ctx.run_with_tools(
        slot="chat",
        system="你是助手，需要时调用工具。",
        user=ctx.query,
        tools=[calc],                          # 本地工具，随代码走
        max_steps=ctx.config.get("max_steps", 6),
    ):
        yield delta
```

### 2. 本地自测（连 dev 服务，无需本地模型凭据）

服务端 `.env` 设 `CHAMELEON_DEV_TOKEN=<token>` 开启 dev 端点，然后：

```bash
pip install "chameleon-agentkit[dev]"
export CHAMELEON_DEV_URL=http://localhost:7009
export CHAMELEON_DEV_TOKEN=<同上 token>

agentkit lint my_agent          # 校验 @agent 声明
agentkit run  my_agent -i "用 calc 算 (123+456)*7"   # 单次跑
agentkit chat my_agent          # 交互 REPL
agentkit dev  my_agent -i "..."  # watch 源文件，改动即热重载重跑（编辑-反馈闭环）
```

模型 / KB / 工具调用经 `HttpDevTransport` 回调站内 dev 服务，用平台已配置资源跑。

### 3. 提交注册

把 agent 包源码提交进 `backend/chameleon-agents/<name>/`（声明 entry-point `chameleon.agents`）。服务端启动发现 + 对账自动建 DB 行 → 注册运行。**同一份代码**站内走 `InProcessTransport` 进程内跑，无需任何改动。

## ctx 能力面（冻结公共 API）

| 能力 | 方法 |
|---|---|
| 模型（低层 LangChain model） | `ctx.llm(slot="chat", model=None)` |
| 模型（高层糖，自动 trace+usage） | `await ctx.complete(...)` / `ctx.stream(...)` |
| 结构化输出 | `await ctx.complete(schema=MyModel, ...)` → 返实例 |
| 工具调用（ReAct 循环糖） | `ctx.run_with_tools(system, user, tools=[...], max_steps=6)` |
| 知识库检索（自动 citation） | `await ctx.kb.search(query, mode="hybrid", rerank=True)` |
| 跨会话记忆 | `await ctx.memory.set/get/all(...)` |
| 检查点/恢复（durable） | `await ctx.checkpoint(state)` / `ctx.restore(default)` |
| 多模态生成 | `await ctx.media.generate(kind="image", prompt=...)` |
| 子智能体编排 | `ctx.call_agent` / `ctx.gather`（并行扇出）/ `ctx.route`（路由）/ `ctx.handoff`（移交） |
| 手动分段 / 透传事件 | `ctx.span(name)` / `ctx.emit(event)` |
| 请求上下文 | `ctx.query / messages / history / session_id / config / attachments` |

声明面 `@agent(...)`：`models` / `kb` / `tools` / `config` / `mcp_servers`（消费外部 MCP）/ `call_agents`（A2A allow-list）/ `sandboxed` + `trust_tier`（不可信代码 docker 隔离）。完整用法见 `docs/agentkit-guide.md`；任务导向食谱（RAG/工具/编排/HITL/MCP/A2A…）见 `docs/agentkit-cookbook.md`。

## 配置双源（代码优先）

每种资源都能在**代码里完全指定**（`ctx.llm(model="qwen-plus")`、`ctx.kb.search(kbs=[...])`、`@tool` 本地工具），web 仅是降低简单 agent 门槛的便捷托管层、非必经。复杂 agent 完全不依赖前端。

冻结纪律：`chameleon.agentkit.__init__` 是公共 API，只增不改；破坏性变更走 major 版本。
