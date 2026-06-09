# agentkit Cookbook —— 任务导向食谱

> 「我要建一个 X agent，怎么写？」——本册按**任务**给最短可跑食谱。每则=场景 + 核心代码 +
> 对应的真实已测示例（`backend/chameleon-agents/examples/`）+ 要点。
> 概念/API 参考见 [agentkit-guide.md](./agentkit-guide.md)；本册只讲「怎么组装」。
>
> 共同前提：每个 agent 是一个 `@agent` 装饰的 `async def handle(ctx)`，`ctx` 由平台隐式注入
> 模型/KB/工具/记忆/trace。本地自测 `agentkit chat my_pkg.agent`，提交进 `chameleon-agents/`
> 即被自动发现、进程内跑。下方代码省略 import（`from chameleon.agentkit import agent, AgentRun, ...`）。

---

## 1. 最小聊天 agent
**场景**：纯对话，单模型一问一答/流式。示例 `echo` · `classic`。
```python
@agent(key="chat", name="聊天助手", models=[ModelSlot("chat", "default")])
async def handle(ctx: AgentRun):
    async for chunk in ctx.stream(user=ctx.query):   # 流式；要整段用 await ctx.complete(...)
        yield chunk
```
**要点**：`models` 声明模型槽，平台按槽绑定实际模型；作者代码不写厂商/key。

## 2. RAG 问答 agent
**场景**：先检索知识库再回答。示例 `rag_qa`。
```python
@agent(key="rag-qa", name="知识问答", models=[ModelSlot("chat", "default")], kb=True)
async def handle(ctx: AgentRun):
    hits = await ctx.kb.search(ctx.query, top_k=5)        # hybrid+rerank 由平台做
    context = "\n".join(h.text for h in hits)
    async for chunk in ctx.stream(system=f"依据资料回答：\n{context}", user=ctx.query):
        yield chunk
```
**要点**：`kb=True` 声明用知识库；检索的混合召回/重排/查询扩展在平台侧，作者只管 `search`。
引用会自动进 trace。

## 3. 工具调用 agent（ReAct 循环）
**场景**：让模型自己决定调哪些工具、循环到收敛。示例 `tool_use`。
```python
@agent(key="calc-bot", name="算术助手", models=[ModelSlot("chat", "default")],
       tools=["calculator"])
async def handle(ctx: AgentRun):
    async for delta in ctx.run_with_tools(user=ctx.query):   # 绑工具→调模型→执行→回灌，循环（流式）
        yield delta
```
**要点**：`tools` 声明平台工具 key；`run_with_tools` 跑完整 ReAct（含并行工具调用 + token 预算闸）。
自定义本地工具用 `@tool` 装饰函数传入。

## 4. 多智能体编排（扇出聚合）
**场景**：并行调多个子 agent，聚合结果。示例 `orchestrator`。
```python
@agent(key="orchestrator", name="编排器", models=[ModelSlot("chat", "default")],
       call_agents=["researcher", "writer"])
async def handle(ctx: AgentRun):
    facts, draft = await ctx.gather([("researcher", ctx.query), ("writer", ctx.query)])
    return await ctx.complete(system="综合下列材料成稿", user=f"{facts}\n{draft}")
```
**要点**：`call_agents` 声明可调的子 agent（白名单）；`gather` 并行扇出且**预算均分防超支**、深度受限。

## 5. 分诊路由 agent
**场景**：按 query 选一个最合适的下游 agent 处理。示例 `triage`。
```python
@agent(key="triage", name="分诊", models=[ModelSlot("chat", "default")],
       call_agents=["sql-bot", "doc-bot", "chat-bot"])
async def handle(ctx: AgentRun):
    return await ctx.route(ctx.query, agents=["sql-bot", "doc-bot", "chat-bot"])
```
**要点**：`route` 让模型选 agent 并转发，返其结果；候选须在 `call_agents` 白名单内。

## 6. 人在环审批 agent（durable HITL）
**场景**：执行高风险动作前暂停等人工批准，恢复后继续——进程重启/跨请求也不丢。示例 `hitl`。
```python
@agent(key="approval", name="审批", models=[ModelSlot("chat", "default")], durable=True)
async def handle(ctx: AgentRun):
    summary = await ctx.complete(system="复述用户要做的操作", user=ctx.query)
    decision = await ctx.ask_human(f"批准以下操作吗？{summary}（同意/拒绝）")  # 暂停点
    yield f"审批结果：{decision}——操作「{summary}」"
```
**要点**：`durable=True` 开启 journal 重放——`ctx.ask_human` 抛暂停，回填答案后 handle **从头重放**
（`complete` 等已记录调用返缓存、不重跑），到 ask 点拿人工答案续跑。**控制流必须确定性**（别依赖
random/时间/未 journal 的状态）。一次性恢复：ask 点定后答案不可翻转。需声明 scope。

## 7. 消费外部 MCP 工具的 agent
**场景**：接入外部 MCP server 的工具（与平台工具混用）。示例 `mcp_use`。
```python
@agent(key="mcp-bot", name="MCP 助手", models=[ModelSlot("chat", "default")],
       mcp_servers=[McpServerConfig(name="math", url="http://localhost:9100/mcp")])
async def handle(ctx: AgentRun):
    async for delta in ctx.run_with_tools(user=ctx.query):   # 外部 MCP 工具自动并入工具集
        yield delta
```
**要点**：`mcp_servers` 声明外部 MCP；本地 `agentkit chat` 也直连（行为与站内一致）。
外部工具与 `tools` 平台工具一起进 ReAct 循环。

## 8. 多模态生成 agent
**场景**：文生图/图生图等。示例 `imagegen`。
```python
@agent(key="image-bot", name="生图", models=[ModelSlot("image", "default")])
async def handle(ctx: AgentRun):
    result = await ctx.media.generate(kind="image", prompt=ctx.query)
    yield f"![generated]({result.url})"
```
**要点**：`ctx.media.generate` 经平台生图供应商（ComfyUI 本地 / DashScope 远程），产物存 MinIO；
成本归集进计费。`kind` 支持 image/video 等。

## 9. 跨系统 A2A：调远程 agent + 暴露自家 agent
**场景**：调用另一套系统的 A2A agent，或把自家 agent 暴露给外部 A2A 客户端。
```python
# 出站：call_agents 里写 http(s) URL，ctx.call_agent 即走标准 A2A 协议调远程
@agent(key="federated", name="联邦", models=[ModelSlot("chat", "default")],
       call_agents=["https://partner.example/a2a/their-agent"])
async def handle(ctx: AgentRun):
    remote = await ctx.call_agent("https://partner.example/a2a/their-agent", input=ctx.query)
    return await ctx.complete(system="结合远程结果作答", user=remote)
```
**入站**：任何已注册 agent 自动在 `/a2a/{key}` 暴露为标准 Agent2Agent（AgentCard 在
`/a2a/{key}/.well-known/agent.json`），外部 A2A 客户端可发现并 `message/send` 调用；durable agent
的 `ask_human` 暂停会映射成 A2A `input-required`，外部客户端带 taskId 回填即续跑。
**要点**：远程 URL 须在 `call_agents` 白名单（防任意 egress）；远程预算/输出按不可信处理；
沙箱 agent 禁出站远程 A2A。对齐 Google A2A 规范。

## 10. 结构化输出
**场景**：要模型返回严格 schema 的结构化数据而非自由文本。
```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

@agent(key="extract", name="抽取", models=[ModelSlot("chat", "default")])
async def handle(ctx: AgentRun):
    person = await ctx.complete(user=ctx.query, schema=Person)   # 返已校验的 Person
    return f"{person.name} / {person.age}"
```
**要点**：`schema=` 传 Pydantic 模型，平台保证返回符合 schema（不符则模型重试）；返回的是模型实例。

---

## 跑法速查
| 命令 | 作用 |
|---|---|
| `agentkit lint my_pkg.agent` | 校验 @agent 声明 |
| `agentkit run my_pkg.agent -i "..."` | 单次跑 |
| `agentkit chat my_pkg.agent` | 交互 REPL |
| `agentkit dev my_pkg.agent -i "..."` | watch 源文件，改动即热重载重跑 |

提交：把包丢进 `backend/chameleon-agents/`（含 `pyproject.toml` 入口点）→ `uv sync` → 自动发现、
进程内跑。离线单测见 guide §5（`chameleon.agentkit.testing` 的 FakeTransport）。
