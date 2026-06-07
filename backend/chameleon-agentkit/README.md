# chameleon-agentkit

Chameleon 编码智能体作者 SDK。**只写业务逻辑**——模型、知识库、工具、追踪都从一个绑定了「本 agent 配置 + 本次请求」的运行时 `ctx` 隐式拿到。同一份代码本地自测通过后，提交进 `chameleon-agents/` 即注册运行。

## 5 分钟 quickstart

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
```

模型 / KB / 工具调用经 `HttpDevTransport` 回调站内 dev 服务，用平台已配置资源跑。

### 3. 提交注册

把 agent 包源码提交进 `backend/chameleon-agents/<name>/`（声明 entry-point `chameleon.agents`）。服务端启动发现 + 对账自动建 DB 行 → 注册运行。**同一份代码**站内走 `InProcessTransport` 进程内跑，无需任何改动。

## ctx 能力面（冻结公共 API）

| 能力 | 方法 |
|---|---|
| 模型（低层 LangChain model） | `ctx.llm(slot="chat", model=None)` |
| 模型（高层糖，自动 trace+usage） | `await ctx.complete(...)` / `ctx.stream(...)` |
| 工具调用（ReAct 循环糖） | `ctx.run_with_tools(system, user, tools=[...], max_steps=6)` |
| 知识库检索（自动 citation） | `await ctx.kb.search(query, kbs=None, top_k=...)` |
| 手动分段 / 透传事件 | `ctx.span(name)` / `ctx.emit(event)` |
| 请求上下文 | `ctx.query / messages / history / session_id / config / attachments` |

## 配置双源（代码优先）

每种资源都能在**代码里完全指定**（`ctx.llm(model="qwen-plus")`、`ctx.kb.search(kbs=[...])`、`@tool` 本地工具），web 仅是降低简单 agent 门槛的便捷托管层、非必经。复杂 agent 完全不依赖前端。

冻结纪律：`chameleon.agentkit.__init__` 是公共 API，只增不改；破坏性变更走 major 版本。
