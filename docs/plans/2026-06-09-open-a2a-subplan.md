# 开放 A2A（T1-3）—— 细化子方案

> 定位：让 agentkit agent 能跨**系统/进程**互调（不止进程内）——MCP 把"外部工具"接进来，
> 开放 A2A 把"外部智能体"接进来 / 把自家智能体作为标准智能体暴露出去。世界顶级框架的互操作
> 入场券（LangGraph / OpenAI Agents SDK 均在补 A2A）。**旗舰级，先出本子方案再动手。**

## 0. 现状（诚实划界）

- **进程内 A2A 已完整**：`ctx.call_agent` / `ctx.gather` / `ctx.handoff` / `ctx.route` 走
  `providers/base/a2a_bridge.py` 的 `A2ACaller(source,target,input,trace_id,budget_remaining,depth)`，
  深度/预算/trace 串联红线齐（含 T4-1 修过的预算注入漏洞 + sanitize_context_vars）。
- **外部暴露 = OpenAI 兼容端点**（`api/openai/`）+ agent_key 作用域鉴权。这是"被外部当 LLM 调"，
  **不是 A2A**（无 AgentCard 能力发现、无 task 生命周期、无 input-required/HITL 语义）。
- **缺口**：① 出站——`ctx.call_agent` 不能 target 一个**远程** A2A agent（只认进程内 key）；
  ② 入站——自家 agent 没有标准 A2A 端点（能力卡 + task 协议），外部 A2A 客户端无法发现/调用。

## 1. 协议决策：对齐 Google **Agent2Agent (A2A)** 规范

不自造协议。对齐事实标准 A2A：
- **AgentCard** `/.well-known/agent.json`：声明 agent 能力/端点/鉴权/streaming 支持。
- **JSON-RPC over HTTP**：`message/send`、`message/stream`(SSE)、`tasks/get`、`tasks/cancel`。
- **Task 生命周期**：`submitted → working → input-required → completed/failed`。
- **理由**：与 MCP 一致的"对齐标准而非自造"策略（评审反复肯定）；A2A 与 MCP 同生态，互补
  （MCP=工具，A2A=智能体）；外部 A2A 客户端（含其它框架）即插即用。

### 关键协同：A2A 的 `input-required` == 我们已建的 durable HITL
A2A task 的 `input-required` 状态语义 = `ctx.ask_human` 暂停。**入站 A2A 暴露可直接复用 durable
HITL**：远程调用方收到 `input-required`（带 pending prompt）→ 回填答案 → `message/send` 续 task
== 我们的 pause→resume。durable 这块不是白做，是 open A2A 的 HITL 地基。

## 2. 两个方向 + 复用

### 出站：`ctx.call_agent("https://other/agent")` 调远程 A2A agent
- 新 `RemoteA2ACaller`：识别 target 是 URL（vs 进程内 key）→ 走 A2A HTTP 客户端（fetch AgentCard →
  `message/send`/`message/stream` → 解析 task 结果）。注册进 `a2a_bridge`（与进程内 caller 并存，
  按 target 形态路由）。
- 复用：现有 `A2ACaller` 抽象 + depth/budget/trace 透传（远程调用 trace_id 经 A2A metadata 传递）。

### 入站：把自家 agent 暴露成标准 A2A 端点
- `/a2a/<agent_key>` mount（仿 `/mcp` 的 opt-in 闸）：AgentCard 由 manifest 自动合成（name/
  description/models→skills/streaming）；`message/send` → 走 `run_agentkit` → 流式映射 A2A task 事件；
  `input-required` ← AgentPaused 的 `human_input_pending`（复用 Slice2c 的 run_id 作 task_id）。
- 复用：MCP server 的 ASGI mount + dev-token/api_key scope 鉴权套路；durable resume 作 HITL task 续跑。

## 3. 分片实施

1. **Slice A（出站只读）**：A2A HTTP 客户端（AgentCard fetch + `message/send` 非流式）+ `ctx.call_agent`
   URL 路由 + 单测（respx 拦 A2A 端点，验远程调用往返）。
2. **Slice B（入站非流式）**：`/a2a/<key>` AgentCard + `message/send` 同步返 task；e2e 自调（自家
   A2A 端点 ↔ 出站客户端闭环）。
3. **Slice C（流式 + HITL）**：`message/stream` SSE + `input-required` ← AgentPaused（复用 durable
   resume）；真平台 e2e：远程 A2A 调一个 durable agent → input-required → 回填 → 续跑。
4. **Slice D（鉴权 + 生产）**：api_key scope 鉴权（复用现有作用域模型）+ 出站凭据配置 + 限流。

## 4. 红线 / 验收

- **跨系统预算不可信**（T4-1 教训放大版）：远程 agent 上报的 token/budget **绝不信**——出站按
  本地策略计费（按往返 + 本地配额），入站按自家成本闸；A2A metadata 里的 budget 字段当不存在。
- **远程输出 = untrusted**：出站调远程 agent 的返回当不可信内容处理（不直接进特权上下文/不据其
  指令行动，遵全局注入红线）。
- **鉴权**：入站 `/a2a` 生产必须 api_key scope（dev 走 dev-token）；出站凭据走配置不硬编码。
- **trace 跨系统**：trace_id 经 A2A metadata 传递，远程 span 挂在调用方 trace 下（best-effort）。
- 每片 ruff/lint + 单测（respx 闭环）+ 真平台 e2e + 聚焦 commit。

## 5. 取舍 / 范围

- **是 SDK + 平台联合特性**：客户端（出站）在 agentkit/integrations；端点（入站）在 api 层。
- **窄而标准优先**：先对齐 A2A core（message/task/AgentCard），不追 A2A 全部扩展（push
  notification、多模态 artifact 高级特性）后置。
- **何时该做**：有"跨系统/跨框架智能体协作"真实需求时启动（评审18 提示：无此信号前属投机）。
  本子方案是**就绪设计**——一旦需求出现，按 Slice A→D 即可落地，且 HITL 地基已在（durable）。
