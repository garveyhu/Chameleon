# T1-1 MCP 双向互操作 —— 细化子方案（旗舰）

> 状态：实现级子方案，待 review → 实施
> 上位：`2026-06-08-world-class-orchestration-roadmap.md` 第 3 节 T1-1（关键路径 #1）
> 定位：**品类入场券**。MCP（Model Context Protocol）是 2025 事实工具标准（Anthropic/
> OpenAI/Cursor/Windsurf 全支持）。缺它 = 用户工具生态为零、agent 进不了别人 IDE。

## 0. 北极星

- **作为 MCP client**：作者一行 `@agent(mcp_servers=[...])`，外部 MCP server（filesystem/
  github/任意第三方）的 tools 自动进 `ctx.run_with_tools` 的 ReAct 循环，与本地 `@tool`、
  平台工具混用。**工具生态 > 自造工具**——不必把每个工具在平台重写一遍 Python 类。
- **作为 MCP server**：平台已注册的 agent + 工具自动暴露成一个 `/mcp` endpoint，让
  Chameleon 的能力能被 Claude Desktop / Cursor / 别的 agent 框架消费。

## 1. 关键架构洞察（决定方案干净度）

**MCP 工具可无损适配成现有 `ToolSpec`，从而零改动复用整条 ReAct 循环。**

证据（已核实真实代码）：
- `agentkit/_spec.py` `ToolSpec(name, description, parameters_schema, handler)` —— 正是
  MCP tool 的形状：MCP tool 有 `name` / `description` / `inputSchema`（JSON Schema）/ 可
  `call_tool(name, args)`。
- `providers/local/agentkit_runner.py` `run_tool_loop` 的调度：tool_call 名 ∈ `local_by_name`
  → 走 `_exec_local(spec, args)` → `await spec.handler(**args)`；∉ → 走平台 `run_tool_calls`。
- **所以**：把每个 MCP tool 适配成 `ToolSpec(name=tool.name, description=tool.description,
  parameters_schema=tool.inputSchema, handler=lambda **a: session.call_tool(name, a))`，
  塞进 `run_with_tools(tools=[...])` 的 `local_tools`，**ReAct 循环、自动 emit tool_call/
  tool_result、trace span、token 预算闸全部免费复用**，一行循环代码都不用改。

这把"接 MCP"从"造新执行路径"降级成"造一个 ToolSpec 适配器 + 连接管理"，是本方案能小而稳的根本。

## 2. 依赖

- chameleon-integrations 加 `mcp`（官方 Python SDK，含 client + server + stdio/SSE/
  streamable-http transports）。当前未装（`import mcp` 失败），需 `uv add` 进 integrations。
- 红线：`mcp` 只进 integrations（厂商实现层），不进 core/agentkit 公共面。

## 3. Phase A — MCP Client（先行，旗舰主体）

### A1. MCP 连接层 `integrations/mcp/client.py`
- `McpServerConfig`（dataclass）：`transport`（stdio/sse/http）+ stdio 的 `command/args/env`
  或 http/sse 的 `url/headers`。
- `MCPSession`：封装 mcp SDK 的 `ClientSession` —— `connect()` / `list_tools()` /
  `call_tool(name, args) -> result` / `aclose()`。统一把 MCP `CallToolResult` 的 content
  （text/image/embedded）摊平成 JSON-able dict（供 ToolMessage 回填）。
- 连接生命周期：MVP **per-request 连接**（handle 开始连、结束关），用 `AsyncExitStack`
  管理。stdio server 冷启有开销，后续可加**连接池/常驻**（按 server config 复用）。

### A2. MCP tool → ToolSpec 适配 `integrations/mcp/adapter.py`
- `async def load_mcp_tools(configs) -> tuple[list[ToolSpec], AsyncExitStack]`：连每个 server
  → list_tools → 每个 tool 造一个 `ToolSpec`：
  - `name`：MCP tool name（多 server 重名加 `server.tool` 前缀消歧）。
  - `parameters_schema`：MCP `inputSchema`（已是 JSON Schema，直接用）。
  - `handler`：闭包 `async (**args) -> dict: r = await session.call_tool(real_name, args); return _flatten(r)`。
- 异常收敛：连不上/list 失败 → 记 warning + 跳过该 server（不拖垮 agent），与现有工具
  执行的容错一致。

### A3. 声明与运行时接线
- `agentkit/_spec.py`：`AgentManifest` 增 `mcp_servers: list[McpServerConfig]`；`@agent(mcp_servers=[...])`。
  `McpServerConfig` 进冻结公共面（agentkit 重导出，但定义在 agentkit，不依赖 mcp SDK——
  纯 dataclass）。
- `agentkit/_runtime.py`：`AgentRun` 增 `ctx.mcp`（可选显式访问；MVP 主路径是自动注入）。
  `RuntimeTransport` 增抽象 `load_mcp_tools(configs) -> (list[ToolSpec], closer)`。
- `providers/local/agentkit_runner.py` `run_agentkit`：构造 transport 时传入 `manifest.mcp_servers`；
  `InProcessTransport` 在 `run_tool_loop` 前经 `integrations.mcp.adapter.load_mcp_tools` 连接 +
  得到 ToolSpec 列表，并入 `local_tools`（与作者 `@tool` 合并）；`run_tool_loop`/handle 结束
  在 `finally` 里 `aclose` 连接栈。
- **配置双源**：代码 `@agent(mcp_servers=)` 点名（档 B 代码优先）；后续可加 web 托管
  MCP server 列表（档 A，存 agents.config，运营可调）。MVP 先代码。

### A4. dev transport
- `HttpDevTransport` 的 MCP：dev 态作者本机直连 MCP server（stdio 在本机更自然）——
  dev 可**本地直接连**（不经 dev 服务回调），即 HttpDevTransport 也用同一 `load_mcp_tools`
  本地连。这样"两种跑法"对 MCP 反而天然一致（MCP server 是外部进程，两端都直连）。

### A5. 示例 + 验证
- `chameleon-agents/examples/mcp_use/`：`@agent(mcp_servers=[stdio filesystem server])`，
  在 `run_with_tools` 里用 MCP filesystem 工具读文件答问。
- e2e：起一个标准 MCP server（如 `@modelcontextprotocol/server-filesystem` 或一个最小
  python stdio server）→ admin-test → 验证 MCP 工具被调用（tool_call/tool_result 事件 +
  trace + 答案用到工具结果）。

## 4. Phase B — MCP Server（把 Chameleon 暴露出去）

### B1. `/mcp` endpoint（chameleon-api）
- 用 mcp SDK 的 server（streamable-http transport）挂一个 `/mcp` 路由。
- 暴露：① 平台已注册的**工具**（integrations/tools registry 的 builtins + 启用工具）作为
  MCP tools；② 可选把**已注册 agent**作为 MCP tools（`call_agent` 语义，一个 agent = 一个
  MCP tool，input=query）。
- 鉴权：复用 api_key scope（MCP 请求带 key，`assert_scope` 校验）。
- 红线：仅暴露**已启用 + 调用方有权限**的工具/agent。

### B2. 发现/文档
- README + docs 增"把 Chameleon 接入 Claude Desktop / Cursor"指南（MCP server 配置片段）。

## 5. 分层与红线
- `mcp` SDK 只进 integrations；agentkit 只持纯 `McpServerConfig` dataclass（不 import mcp）。
- 适配器把 MCP tool 归一成 `ToolSpec` → 走既有循环，**不新建执行路径**（§8 路线图致命风险
  #1「私有协议锁死」的正解：MCP 是开放标准，经 ToolSpec 这层适配接缝接入，内核不被私有
  假设固化）。
- 连接生命周期必须 `finally` 关闭（防 stdio 子进程/HTTP 连接泄漏）。
- 第三方 MCP server = 外部代码/网络，多租户下需与沙箱（T4-2）配合（不可信 agent 的 MCP
  连接也应在沙箱内），MVP 限受信 server。

## 6. 分期与验收

| 阶段 | 内容 | 验收 |
|---|---|---|
| A1+A2 | mcp 依赖 + 连接层 + ToolSpec 适配 | 单测：mock MCP session → list_tools → 适配成 ToolSpec → handler 调通 |
| A3 | @agent(mcp_servers=) + 运行时接线 + 生命周期 | 单测：manifest 带 mcp_servers，runner 连接 + 并入 local_tools + finally 关闭 |
| A4+A5 | dev 本地直连 + example-mcp-use + e2e | 真实 MCP filesystem server → admin-test 调用工具成功，trace 出 tool_call/result |
| B1 | /mcp server endpoint | Claude Desktop / mcp inspector 连上 → 列出并调用平台工具 |
| B2 | 文档 | 接入指南可复现 |

每阶段 ruff/lint 2 契约 GREEN + 单测 + 真实 e2e + 聚焦 commit。

## 7. 风险与开放问题
- **stdio server 冷启开销**：per-request 连接对高频 agent 慢 → A1 后加连接池/常驻（按 config 复用）。
- **多 server 工具重名**：用 `server.tool` 前缀消歧（A2）。
- **MCP server 暴露面**（Phase B）：必须经 key scope 鉴权，仅暴露已启用工具，防越权。
- **不可信 MCP server**：第三方 server 可能返恶意内容/超大 payload → 适配器对 content 做大小
  截断 + 类型白名单（同现有工具 result 处理）。
- **MCP SDK 版本/transport 演进**：streamable-http 是较新 transport，stdio/sse 兼容旧；
  client 层抽象掉 transport 差异。
