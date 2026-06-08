# agentkit 作者指南 —— 代码即真相的智能体开发

Chameleon 的 `agentkit` 让你**只写业务逻辑**：声明一个 `@agent`、实现 `handle(ctx)`，
平台隐式接管模型、知识库、工具、子智能体、记忆、多模态、追踪、计费、MCP 互操作、嵌入式
分发。同一份代码两种跑法——本地 `agentkit chat` 离线自测、提交后站内进程内运行，行为一致。

> 公共面 `chameleon.agentkit` 是冻结契约（只增不改）。`chameleon.agentkit.testing` 同。

## 1. 起步：一条命令

```bash
agentkit new weather-bot          # 生成 weather-bot/ 包骨架（pyproject + 最小 @agent 样板）
# 编辑 weather-bot/src/chameleon/agents/weather_bot/agent.py，写业务逻辑
# 丢进 backend/chameleon-agents/ → 起服务即被自动发现（无需改 app 依赖）
```

最小 agent：

```python
from chameleon.agentkit import agent, AgentRun, ModelSlot

@agent(key="weather-bot", name="天气助手", models=[ModelSlot("chat", "对话模型")])
async def handle(ctx: AgentRun):
    async for delta in ctx.stream(slot="chat", system="你是天气助手。", user=ctx.query):
        yield delta
```

## 2. ctx —— 平台隐式提供的全栈能力

| 能力 | 用法 | 平台代管 |
|------|------|----------|
| 文本生成 | `await ctx.complete(slot="chat", user=...)` / `async for d in ctx.stream(...)` | 模型路由 / 凭据 / trace / 计费 |
| 结构化输出 | `await ctx.complete(schema=MyModel, user=...)` → 返 `MyModel` 实例 | with_structured_output |
| 知识库检索 | `docs = await ctx.kb.search(ctx.query, mode="hybrid", rerank=True)` | 向量+BM25 混合 / rerank / 查询扩展 / 自动引用 |
| 工具循环（ReAct） | `async for d in ctx.run_with_tools(user=..., tools=[my_tool], tool_keys=["http"])` | 平台工具闸门 / 本地 @tool / 自动 tool_call·result 事件 |
| 跨会话记忆 | `await ctx.memory.set(k, v)` / `await ctx.memory.get(k)` | KV 按 end_user 隔离 |
| 多模态生成 | `await ctx.media.generate(kind="image", prompt=..., model=...)` | ComfyUI/DashScope 路由 + MinIO 存储 + 计费 |
| 子智能体（A2A） | `await ctx.call_agent("other-agent", input=...)` | 进程内 A2A + 深度/预算闸 |
| 自定义追踪段 | `async with ctx.span("retrieve"): ...` | 自动 trace 树 + rollup |
| 逃生口 | `m = ctx.wrap(my_langchain_model)` | 用自带模型（绕路由/计费，极端定制） |

模型多槽：`@agent(models=[ModelSlot("chat"), ModelSlot("fast")])` → `ctx.complete(slot="fast")`。

## 3. 声明（`@agent` 参数）

```python
@agent(
    key="...", name="...", description="...", tags=[...],
    models=[ModelSlot("chat", "对话")],         # 具名模型槽（web 绑具体 model code）
    kb=True,                                     # 启用知识库检索
    tools=["http", "sql"],                       # 可用平台工具集（web 可启停子集）
    config=[Opt("temperature", "温度", default=0.7)],  # 运营可调项；ctx.config["temperature"] 取 default←web 覆盖
    mcp_servers=[McpServerConfig(...)],          # 外部 MCP server，其 tools 自动进 run_with_tools（见 §6）
    call_agents=["sub-agent"],                   # 可经 ctx.call_agent 调的子 agent（沙箱下强制白名单）
    sandboxed=True,                              # 不可信代码隔离执行（见 §7）
)
```

**配置双源代码优先**：每个资源都能在代码里声明齐全，web 仅作便利覆盖层。

## 4. 本地开发回路（不连站内也能自测）

```bash
export CHAMELEON_DEV_TOKEN=<与服务端一致>
agentkit lint my_pkg.agent                       # 校验 @agent 声明
agentkit run  my_pkg.agent -i "北京天气"          # 单次跑（ctx 经 HttpDevTransport 回调站内资源）
agentkit chat my_pkg.agent                        # 交互 REPL
```

dev 态 ctx 的模型/KB/工具/结构化/记忆/子智能体/MCP 工具都经 `/v1/dev/*` 用站内已配置资源跑，
作者无需本地凭据。每轮答完打印本地 **trace 树**（各段耗时+嵌套）。

## 5. 离线单测（`chameleon.agentkit.testing`）

```python
from chameleon.agentkit.testing import FakeTransport, make_run, collect

async def test_answers():
    t = FakeTransport(replies=["北京晴"], kb=[Doc(text="北京 天气晴")])
    run = make_run(handle, query="北京天气", transport=t)
    out = await collect(handle(run))
    assert "晴" in out
```

`FakeTransport` 可编程 replies/kb/tool_calls/structured/memory/media/call_agent，记录
`invocations`/`tool_invocations`。完全离线、确定性，无需服务。

## 6. MCP 双向互操作

**消费外部 MCP server**（你的 agent 用别人的工具）：

```python
from chameleon.agentkit import McpServerConfig

@agent(key="...", mcp_servers=[
    McpServerConfig(name="fs", transport="stdio", command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/data"]),
])
async def handle(ctx):
    # filesystem server 的 tools 自动进 ReAct 循环，与本地 @tool/平台工具混用
    async for d in ctx.run_with_tools(user=ctx.query):
        yield d
```

**把 Chameleon 暴露给外部 MCP client**（Claude Desktop / Cursor 调你的平台工具与 agent）：
开发态设 `CHAMELEON_DEV_TOKEN` 后 `/mcp` endpoint 上线，暴露平台工具 + 每个 agent（`agent.<key>`）。
客户端配置（streamable-http + `X-Dev-Token` 头）即可 `list_tools` / `call_tool`。
> 生产对外开放需补 api_key scope 鉴权（路线图在办）。

## 7. 不可信代码隔离（`sandboxed=True`）

`@agent(sandboxed=True)` 声明该 agent 需隔离执行。运行档由部署决定：

- **dev / 默认**：进程内（便利）。
- **生产真隔离**（`CHAMELEON_SANDBOX_RUNTIME=docker` + `CHAMELEON_SANDBOX_IMAGE`）：handle 在
  `--network none --read-only --user nobody --cap-drop ALL` 的 docker 容器内跑，**无凭据、无
  网络、无文件系统访问**；ctx 资源调用经 stdio JSON-RPC 回主进程 broker 受控解析，broker 施加
  scope 红线（只能用声明的 model/tool/kb/call_agent）。镜像见 `docker/sandbox.Dockerfile`。
- 子进程档（半可信）：env 凭据擦除 + CPU/进程限，但不隔离 FS/网络。

凭据/DB 永远只在主进程；不可信 agent 代码碰不到。

## 8. 平台还提供什么（你不用操心的）

- **可观测**：每次调用自动落 call_log trace 树（LangFuse 式），token/成本 rollup；可经
  `CHAMELEON_OTEL_EXPORT_ENDPOINT` 出站到 LangSmith/Langfuse/Phoenix（GenAI semconv）。
- **计费**：模型 token + 媒体生成成本自动归集进根行；A2A 子调用累计预算闸。
- **嵌入式分发**：agent 可作为 OpenAI 兼容端点 / 嵌入式 widget 对外。
- **会话**：history / end_user 身份 / 附件多模态自动注入 messages。

一句话：**建文件夹、写 `handle(ctx)`、声明用什么——其余平台全包。**
