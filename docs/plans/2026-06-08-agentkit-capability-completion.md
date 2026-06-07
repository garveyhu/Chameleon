# agentkit 能力补全 —— 从「RAG / Chat」到完整编码智能体 SDK

> 状态：实现方案（SSOT），待 review → 实施
> 前置：`docs/plans/2026-05-26-local-agent-sdk.md`（Phase 0–4 已完成）
> 目标读者：框架维护者 + 未来用 SDK 接入的外部开发者

## 1. 背景与目标

[[local-agent-sdk-plan]] 的 Phase 0–4 已把 agentkit 的**底座**做扎实：冻结公共面（`@agent` + `AgentRun` + `ModelSlot` / `Opt` / `Doc`）、多具名模型槽 + web 绑定链、KB 隐式联动 + 自动 citation、配置 Schema → 自动表单、entry-points 发现 + 代码即真相的 DB 对账。

但 `ctx` 当前能做的只有：**调模型（`complete`/`stream`/`llm`）、检索（`kb.search`）、出文本**。这是「带检索的 chatbot」能力面，撑不起平台「**以代码为核心，为编码智能体提供一切组件**」的定位。一个现代 agentic / 编码智能体的核心行为——**工具调用、多步推理循环、结构化输出、子智能体编排、记忆、可信执行**——SDK 一个都没暴露。

**关键判断**：缺口集中在「能力表面」而非「地基」。平台引擎层（`chameleon-engine` / `chameleon-integrations`）**已经具备**这些能力的完整实现，只是被 graph 节点独占、没有透出到 agentkit 的 `ctx`。因此本方案的主轴是：

> **把引擎已有的 agentic 设施，按「配置双源 / 代码优先」哲学收口到 `AgentRun` 的公共面上。复用为主，新建为辅。**

目标：完成后，作者用同一套 `ctx` 既能写一行 RAG，也能写带工具循环、子智能体协作、结构化输出、跨会话记忆的复杂编码智能体；外部开发者能离线开发自测后提交注册。达到「商业可用的代码智能体平台」标准。

## 2. 设计原则（贯穿全程）

1. **复用引擎设施，不重造**。tool-loop 原语、A2A、沙箱、observe 都已存在，agentkit 只做「作者友好门面 + 自动 trace/事件收口」。
2. **配置双源、代码优先**（延续设计文档 §3.1）。每种资源（模型 / KB / 工具 / 子智能体）都必须能在**代码里完全指定**，web 仅是降低简单 agent 门槛的便捷托管层、非必经。
3. **公共面只增不改**。`chameleon.agentkit.__init__` 是冻结契约；新增字段 / 方法只增量，破坏性变更走 major 版本。内部实现（transport / 解析 / 循环）随意重构。
4. **分层不被打破**。`core ← data ← integrations ← engine`；agentkit 包只依赖 `core` + `providers.base.types`；runner 在 `providers-local`。tool-loop 原语先下沉到 `integrations/tools`（在 engine、providers 之下），避免 `providers-local → engine` 耦合。
5. **trace 不断链**。所有新能力沿用 `observe` + `_scoped_observation_id` 把 span 锚到 trace 根，保证根行 rollup（token/cost/model）正确——这是 [[observability-langsmith]] 的红线。
6. **每期可验证**：tsc/ruff + 单测 + e2e + 浏览器截图存证（[[implementation-review]] / [[feedback-verify-ui-in-browser]]）。

## 3. 能力缺口总览（实施顺序）

| 编号 | 能力 | 优先级 | 引擎设施现状 | 工作量主轴 |
|---|---|---|---|---|
| **R0** | tool-loop 原语下沉到 integrations | 准备 | 原语在 `engine/graph/nodes/{llm_tools,tool}.py` | 搬迁 + 解耦 |
| **P0-1** | 工具调用（双源 + ReAct 循环）| 🔴 P0 | `bind_tools`/`run_tool_calls`/`run_tool`/Tool registry 全有 | ctx 表面 + DB 列 + 前端 tab |
| **P0-2** | 本地开发闭环（CLI + dev 端点）| 🔴 P0 | 无（Phase 5 整期未动）| 新建 CLI + transport + 端点 |
| **P1-1** | 结构化输出 `complete(schema=)` | 🟠 P1 | langchain `with_structured_output` | ctx 表面糖 |
| **P1-2** | 子智能体 / A2A `ctx.call_agent` | 🟠 P1 | `engine/agent/a2a.py` 完整（预算/深度/trace 红线）| ctx 收口 + 预算透传 |
| **P1-3** | 记忆 `ctx.memory`（kv + 向量）| 🟠 P1 | sessions 表 + 向量库 | 新表 + transport 方法 |
| **P1-4** | 类式 `@agent` 补全 ctx 注入 | 🟠 P1 | runner `is_class` 分支只裸调 astream | runner + BaseAgent 桥 |
| **P1-5** | 沙箱执行（可信边界）| 🟠 P1 | `SandboxRuntime` 协议 + docker/mock | runner 可选路由 |

## 4. 现有可复用设施盘点（实施前必读）

| 设施 | 位置 | 可复用 API |
|---|---|---|
| Tool 协议 | `core/tools/base.py` | `Tool`（`tool_key`/`description`/`parameters_schema()`/`async run(args, ctx)`/`run_with_validation`）、`ToolContext`、`ToolResult` |
| Tool registry | `integrations/tools/registry.py` | `register_tool` / `get_tool_class` / `list_tool_keys` / `all_tool_classes` |
| 内置工具 | `integrations/tools/builtins/` | `http` / `sql` / `code_runner`（后两者 `default_enabled=False`）|
| ReAct 原语 | `engine/graph/nodes/llm_tools.py` | `bind_tools(client, tool_keys)` / `extract_tool_calls(ai_msg)` / `extract_usage` / `merge_usage` / `run_tool_calls(...)` |
| 工具执行入口 | `engine/graph/nodes/tool.py` | `async run_tool(name, args, *, caller, related_id, extra)` |
| A2A | `engine/agent/a2a.py` | `call_agent(source, target, input, trace_id, budget_remaining, depth, ...)`，红线：trace_id 必传 / budget>0 / depth<3 |
| 沙箱 | `core/sandbox/runtime.py` + `integrations/sandbox/` | `SandboxRuntime`（ABC）/ `register_runtime` / `get_runtime` / `is_production` / `bootstrap_runtimes()` |
| observe | `core/observe/context.py` | `observe(observation_type, name, request_id=...)` / `current_observation_id` / `current_trace_context` |
| 流事件 | `providers/base/types.py` | `StreamEventType.{delta,tool_call,tool_result,citation,step,metadata,done,error}` —— **tool 事件线协议已就绪** |
| registry 注入点 | `providers/base/registry.py:329` | `build_agent_registry_from_db` 把 `__agentkit_module__/__agentkit_attr__/model_bindings` 注入 `agent_def.config` |

> **结论**：StreamEventType 早有 `tool_call`/`tool_result`，`InvokeResult.tool_calls` 也在 → 工具调用的「线协议 + 执行 + 循环」全齐，**P0-1 主要是 SDK 表面工作**。

---

## R0 — tool-loop 原语下沉到 integrations（准备步，解耦）

**问题**：`run_tool` / `bind_tools` / `run_tool_calls` 逻辑通用，但物理位置在 `engine/graph/nodes/`；`providers-local`（agentkit runner 所在）依赖链是 `core/integrations/providers-base/agentkit`，**不含 engine**。直接 import 会引入 `providers-local → engine` 耦合（虽 `providers-graph` 已这么做，但 tool-loop 与 graph 无关，不该绑死）。

**做法**：
1. 新建 `integrations/tools/loop.py`，把 `bind_tools` / `extract_tool_calls` / `extract_usage` / `merge_usage` 这些**与 graph 无关的纯函数**从 `engine/graph/nodes/llm_tools.py` 搬入（去掉 `NodeContext` 依赖，改收通用参数）。
2. 新建 `integrations/tools/execute.py`，把 `run_tool(name, args, *, caller, related_id, extra)` 从 `engine/graph/nodes/tool.py` 搬入（它本就只依赖 registry + `ToolContext` + sandbox，零 graph 依赖）。
3. `engine/graph/nodes/{llm_tools,tool}.py` 改为从 `integrations.tools.{loop,execute}` re-export，graph 节点调用零改动（[[feedback-no-deprecation-wrapping]]：内部模块，直接改 import，不留 @deprecated）。
4. 校验：`lint-imports` 两契约仍 GREEN；graph tool 节点单测（`test_graph_llm_tool_calls`、`test_e2e_tool_node_gate`）全绿。

**产出**：`integrations.tools` 成为工具能力的唯一中台，graph 节点与 agentkit runner 共用同一执行 / 循环原语，不分叉。

---

## P0-1 — 工具调用（双源 + ReAct 循环）

### 设计：两档工具来源（代码优先）

| 档 | 写法 | 谁决定 |
|---|---|---|
| **代码自定义工具（核心、最 agentic）** | `@tool` 装饰作者自己的 async 函数 → 传进循环 | 完全代码控制，随 agent 代码走，不入平台 registry |
| **平台托管工具（便捷）** | `@agent(tools=["http", "sql"])` 点名 registry 已注册工具；web「关联工具」tab 勾选启用子集 | 代码声明可用集，运营 web 调启停 |

两档可混用：作者既写本地 `@tool`，又点名平台 `http`，循环里统一调度。

### 公共面增量（`chameleon.agentkit`）

```python
# 新增：作者声明本地工具
@tool(name="get_weather", description="查询城市当前天气")
async def get_weather(city: str) -> dict:
    ...
# @tool 从函数签名（或 pydantic 入参）推断 parameters_schema；产出 ToolSpec（name/description/schema/fn）

# @agent 新增 tools= 声明平台工具点名（可空）
@agent(key="assistant", name="带工具助手",
        models=[ModelSlot("chat")],
        tools=["http"],                      # 平台 registry 工具点名
        config=[Opt("max_steps", type="number", default=6)])
async def handle(ctx: AgentRun):
    # 高层糖：自动 ReAct 循环（本地 @tool + 平台工具混用），yield 最终文本增量
    async for delta in ctx.run_with_tools(
        system="你是助手，需要时调用工具。",
        user=ctx.query,
        tools=[get_weather],                  # 追加本地工具；平台工具来自 @agent(tools=) 或这里加字符串 "http"
        max_steps=ctx.config.get("max_steps", 6),
    ):
        yield delta
    # 工具调用 / 结果自动 emit 成 tool_call / tool_result 事件（同 kb 自动 citation 模式）
```

低层逃生口（power user）：`ctx.llm("chat").bind_tools([...])` 直接拿绑好工具的 langchain model，自己写循环。

### 运行时实现

1. **`_spec.py`**：`AgentManifest` 增 `tools: list[str]`（平台点名）；新增 `ToolSpec`（name/description/parameters_schema/handler）。`_decorator.py` 增 `@tool` 装饰器（签名 → JSON Schema 推断，复用 `core/tools` 的简单 schema 形态）。
2. **`_runtime.py` `RuntimeTransport`** 增抽象：
   - `bound_chat_model(slot/model, tool_keys, local_tools) -> model`（绑平台 + 本地工具的 schema）
   - `async exec_tool(name, args) -> dict`（平台工具走 registry / 本地工具走 callable，统一返 dict）
3. **`AgentRun.run_with_tools(...)`**（新方法，async iterator）：ReAct 循环——
   - 复用 `integrations.tools.loop`：`extract_tool_calls` / `extract_usage` / `merge_usage`。
   - 每轮：`model.ainvoke(msgs)` → 抽 tool_calls → 无则 yield 最终文本、结束；有则 `transport.exec_tool` 跑每个工具 → `emit(tool_call)` + `emit(tool_result)` → 回填 `ToolMessage` → 下一轮。
   - 整体套 `span("agent.tools")`，每轮 LLM 调用 / 工具执行各自子 span，usage 累加 → trace 树完整、token/cost 归集正确。
   - `max_steps` 上限（防无限循环），超限 emit 一个 `step` 事件说明截断。
4. **`InProcessTransport`（agentkit_runner.py）**：实现两个新方法——`bound_chat_model` 用 `integrations.tools.loop.bind_tools` 把平台 tool_keys + 本地 ToolSpec schema 绑到 `llm_by_name(code)`；`exec_tool` 本地工具直调 callable、平台工具走 `integrations.tools.execute.run_tool`。
5. **平台工具集解析**：`@agent(tools=[...])` 声明的可用集 ∩ web `tool_bindings`（启用子集）= 本次实际绑定的平台工具。

### 存储 + 注册 + 前端

- **DB**：新增列 `agents.tool_bindings JSON`（启用的平台 tool_key 列表）。迁移 `pXX_xx_agent_tool_bindings.py`（SQLite 用 `batch_alter_table`，[[coding-standards]]）。
- **registry**：`build_agent_registry_from_db`（registry.py:329 附近）注入 `config["tools"] = manifest.tools`、`config["tool_bindings"] = row.tool_bindings`。
- **API**：`GET /v1/admin/agents/{id}/tools`（返声明可用集 + 当前启用 + 每个工具 description/schema）、`POST /v1/admin/agents/{id}/tools/update`（写 tool_bindings）。handler 零业务，调 service（[[feedback-api-no-logic]]）。
- **前端**：详情页新增「关联工具」tab（仅 `tools` 非空时显示），镜像 `linked-models-form.tsx` 模式：列声明的平台工具 + 开关 + description。本地 `@tool` 只读展示（代码控制，web 不可改）。
- **示例**：新增 `chameleon-agents/examples/tool_use/`（一个本地 `@tool` 计算器 + 平台 `http` 混用，`run_with_tools` 循环），声明 entry-point，作 SDK 工具用法范例。

### 验证

- 单测：`@tool` schema 推断、ReAct 循环（mock model 出 tool_call → 工具执行 → 二轮出文本）、max_steps 截断、本地/平台混用调度。
- e2e：真实 LLM + `http` 工具跑通，`call_logs` 工具子观测进 trace 树、usage 累加正确。
- 浏览器：详情页「关联工具」tab 渲染 + 启停保存 + playground 跑出 tool_call / tool_result 卡片。

---

## P0-2 — 本地开发闭环（Phase 5：CLI + dev 端点）

兑现「开发者 `pip install chameleon-agentkit` → 本地写 → 自测 → 提交注册」的离线闭环。同一份作者代码两种跑法：本地 `HttpDevTransport`（连 dev 服务）/ 站内 `InProcessTransport`。

### 组件

1. **`HttpDevTransport`**（`agentkit/_dev_transport.py`）：实现 `RuntimeTransport` 全部抽象方法，把 `chat_model`/`kb_search`/`exec_tool`/`span`/`emit` 转成对 dev 服务的 HTTP 回调。
   - `chat_model` 走 dev 服务的 LLM 代理端点（返回一个 duck-typed 的 `ainvoke/astream` 远程客户端，不本地持凭证）。
   - `kb_search` / `exec_tool` 走对应 dev 端点。
   - span/emit 走 trace 端点（或本地控制台打印，二选一可配）。
2. **dev 端点**（`chameleon-api`，`/v1/dev/*`，仅非生产 profile 开 + dev token 鉴权）：
   - `POST /v1/dev/llm`（slot/model + messages → 调用平台模型，回流式 / 文本）
   - `POST /v1/dev/kb/search`
   - `POST /v1/dev/tools/exec`
   - `POST /v1/dev/trace`（接收 span/事件落 call_logs，开发态可见）
   - 鉴权：复用 [[api-key-scope-model]] 的 key 机制，新增 `scope_type='dev'` 或专用 dev token；生产环境端点整体不挂载。
3. **CLI**（`agentkit` console_scripts，`agentkit/_cli.py`）：
   - `agentkit chat <module:attr>`：import 作者模块 → 取 manifest → 起 REPL，每轮调 `handle(ctx)`（ctx 背后 `HttpDevTransport` 连 `localhost:7009`），打印增量 + 工具事件 + trace。
   - `agentkit run <module:attr> --input "..."`：单次非交互跑。
   - `agentkit lint <module>`：校验 manifest（key 唯一 / 槽声明合法 / tools 存在）。
   - 配置：`CHAMELEON_DEV_URL` + `CHAMELEON_DEV_TOKEN` 环境变量 / `.env`。
4. **`pyproject.toml`**：`[project.scripts] agentkit = "chameleon.agentkit._cli:main"`；CLI 依赖（httpx / typer 或 argparse）放可选 extra `agentkit[dev]`，避免站内运行时被 CLI 依赖污染。

### 文档

- `chameleon-agentkit/README.md`：quickstart（5 分钟从零写一个带工具的 agent → 本地自测 → 提交）。
- 文档站「指南页」增 agentkit 开发者指南（复用现有文档站能力，commit b810517 的指南页支持）。

### 验证

- e2e：起 7009 dev profile → `agentkit chat example-rag-qa` 本地连通、出真实回复 + 引用 + trace。
- 同一份 `example-tool-use` 代码：本地 `HttpDevTransport` 跑通 == 提交后 `InProcessTransport` 跑通（两跑法一致性）。

---

## P1-1 — 结构化输出 `ctx.complete(schema=...)`

作者要 JSON / 抽取结果时不再手解析。

```python
class Triage(BaseModel):
    category: Literal["闲聊", "技术", "投诉"]
    confidence: float

result: Triage = await ctx.complete(slot="fast", user=ctx.query, schema=Triage)
```

- `AgentRun.complete` 增 `schema: type[BaseModel] | None`；非空时 transport 返 `model.with_structured_output(schema)`（langchain 原生），`ainvoke` 直接返实例（不经 `_content_to_text`）。
- transport 增 `structured_model(slot/model, schema)`；`InProcessTransport` 用 `llm_by_name(code).with_structured_output(schema)`。
- 自动 span + usage 照旧（结构化调用底层仍是一次 generation）。
- 校验：mock 模型返合规 JSON → 得 pydantic 实例；不合规 → 复用 langchain 重试 / 报错。

## P1-2 — 子智能体 / A2A `ctx.call_agent`

收口已完整的 `engine/agent/a2a.py`，作者一行调另一个已注册 agent，红线（trace 不断链 / 预算 / 深度）自动满足。

```python
res = await ctx.call_agent("critic", input=draft)   # 返子 agent 的文本 / 结构化结果
```

- `AgentRun.call_agent(target, *, input)`：transport 调 `engine.agent.a2a.call_agent`，自动填：`source=ctx.agent_key`、`trace_id=` 当前 trace 根、`depth=` 当前深度 + 1、`budget_remaining=` 从 ctx 透传的剩余预算。
- **分层注意**：`a2a` 在 engine，`providers-local` 不依赖 engine → transport 经一个注入的桥（仿 `bridge_registry` / `ObservationSink` 的 IoC 模式：`set_a2a_caller()` 在 app 启动注入），agentkit / runner 不直接 import engine。
- ctx 需携带 `budget_remaining` + `depth`（从 InvokeContext.context_vars 的 `_a2a_*` 读，或 service 初始预算下发）。
- 自动 emit `step` 事件标记子调用；子 agent 的 observation 已挂当前 trace 树（a2a 内部 `observe` 处理）。
- 校验：复用 `test_a2a` + 新增 ctx 层 e2e（proposer → critic 两 agent，trace 树双层、预算递减）。

## P1-3 — 记忆 `ctx.memory`（跨会话状态）

`history` 只是本会话消息；agentic agent 需要跨会话的 kv / 向量记忆。

- **kv 记忆**（先做）：`ctx.memory.get(key)` / `ctx.memory.set(key, value)` / `ctx.memory.all()`。作用域：`(agent_key, end_user_id)` 或 `(agent_key, session_id)`，作者声明。落新表 `agent_memory(agent_key, scope_ref, key, value JSON, updated_at)`（迁移 + service）。
- **向量记忆**（后做，可选）：`ctx.memory.recall(query, top_k)` —— 把历史片段写进一个 agent 私有向量集合，语义召回。复用现有向量库设施（[[kb-dify-parity]] 的 ingest / search），作用域隔离。
- transport 增 `memory_get/set/recall`；`InProcessTransport` 直连新 service。
- **身份依赖**：作用域用 [[session-observability-refactor]] 的 `end_user_id` 身份层；无身份退化为 session 级。
- 校验：set → 新 session get 命中；向量 recall 召回相关片段。

## P1-4 — 类式 `@agent`（BaseAgent）补全 ctx 注入

**现状 bug**：`agentkit_runner.py` 的 `is_class` 分支只 `target.astream(ctx)`（裸 InvokeContext），**完全没注入 AgentRun / transport** → 有状态 / 多节点 agent 拿不到 `ctx.llm/kb/tools/trace` 任何便利。设计文档「两层共用同一 ctx」的承诺对类式路径未兑现。

- **做法**：`BaseAgent` 增一个可选钩子 `async def handle(self, run: AgentRun)`（或 `astream(self, run: AgentRun)`），runner 的 `is_class` 分支构造 `AgentRun` + transport 后注入，与函数式同源。
- 旧 `astream(ctx: InvokeContext)` 签名保留兼容（底层路径）；新写法收 `AgentRun`。runner 按是否声明新钩子分发。
- 保留至少一个 `BaseAgent` 写法范例（多节点 / 自定义状态机），证明高级路径同样吃到 ctx 全部能力。
- 校验：一个有状态类式 agent（计数器 / 多节点）用 `ctx.complete` + `ctx.tools` 跑通。

## P1-5 — 沙箱执行（可信边界）

**现状**：提交进 `chameleon-agents/` 的代码跑在**主进程**，等同完全信任源码（靠 PR review 兜）。多租户 / 接受外部不可信 agent 代码时是安全红线。

- **做法**：runner 增可选「沙箱执行」路由——`@agent(sandboxed=True)` 或平台策略标记的 agent，其 `handle` 在 `SandboxRuntime`（`integrations/sandbox` 的 docker runtime）里跑，ctx 的资源调用经受控 RPC 回主进程（类似 `HttpDevTransport` 但走沙箱内 transport）。
- 复用 `core/sandbox/runtime.py`（`get_runtime` / `is_production`）+ `bootstrap_runtimes`。Code 节点已有 docker runtime 可借鉴。
- **范围**：发布前可只做「设计 + 接口预留 + 默认进程内」，真正 docker 隔离按商业租户需求排期（性能 / 启动开销权衡）。
- 校验：mock runtime 下 sandboxed agent 跑通；docker runtime 下资源回调（llm/kb/tool）经 transport 正常。

---

## 5. 公共面增量清单（冻结 API 的新增项）

`chameleon.agentkit.__all__` 新增（**只增不改**）：

```python
# 装饰器
tool                       # @tool 声明本地工具
# 声明类型
ToolSpec                   # @tool 产物
# AgentManifest 增字段：tools: list[str]
# AgentRun 增方法：
#   run_with_tools(*, system, user, tools=[], max_steps=...) -> AsyncIterator[str]   (P0-1)
#   complete(..., schema=PydanticModel) -> BaseModel                                  (P1-1)
#   call_agent(target, *, input) -> str | BaseModel                                   (P1-2)
#   memory: MemoryHandle  (.get/.set/.all/.recall)                                    (P1-3)
# RuntimeTransport 增抽象：bound_chat_model / exec_tool / structured_model /
#   call_agent / memory_* （内部，非作者面）
```

冻结纪律：作者面方法签名只增可选参数；transport 抽象是内部、可随意演进。

## 6. 分期与里程碑

| 期 | 内容 | 交付 |
|---|---|---|
| **R0** | tool-loop 原语下沉 integrations | lint GREEN + graph 工具测试绿 |
| **P0-1** | 工具调用（双源 + ReAct）+ DB + API + 前端 tab + 示例 | e2e 真实工具调用 + trace + 浏览器截图 |
| **P0-2** | CLI + HttpDevTransport + dev 端点 + README quickstart | 本地 `agentkit chat` 连通 + 两跑法一致 |
| **P1-1** | 结构化输出 | 单测 + e2e |
| **P1-2** | A2A `ctx.call_agent`（IoC 桥）| 双 agent trace 树 e2e |
| **P1-3** | kv 记忆（向量记忆可拆子期）| 跨 session 命中 e2e |
| **P1-4** | 类式 @agent 补全 ctx | 有状态类式 agent e2e |
| **P1-5** | 沙箱（接口预留 + mock；docker 按需）| mock runtime 跑通 |

每期独立 commit，分支策略沿用当前 `refactor/newapi-gateway` 或新切 `feat/agentkit-capabilities`（建议后者，隔离发布前大改）。

## 7. 风险与开放问题

1. **进程内信任边界**（P1-5）：发布前默认进程内 + PR review；docker 隔离的启动开销 / 资源回调延迟需压测后定是否对多租户强制。
2. **A2A 预算来源**：ctx 的 `budget_remaining` 从哪下发？需 service 层在 invoke 入口算初始预算（按 app 配额 / key 限额）写进 context_vars，agentkit 透传。未接则 a2a 红线 `budget>0` 会拒。
3. **本地工具 schema 推断**：`@tool` 从函数签名推断 JSON Schema 的覆盖度（pydantic 入参 / typing 注解 / 默认值）。MVP 支持基本标量 + pydantic model 入参，复杂类型报清晰错误。
4. **dev 端点暴露面**：`/v1/dev/*` 必须仅非生产 profile 挂载 + dev token；误开 = 模型调用 / 工具执行裸暴露。
5. **ReAct 循环成本失控**：`max_steps` 必须有默认上限；建议同时接 A2A 式 token 预算，循环内累计超限即截断。
6. **结构化输出模型兼容**：`with_structured_output` 依赖模型支持 function calling / json mode；不支持的模型需降级提示（prompt 强约束 + 解析兜底）。

## 8. 验证策略（每期）

- `ruff` + `tsc` + `eslint`（[[frontend-build-gotchas]]）。
- 单测随包：agentkit 契约测试（`tests/test_agentkit_contract.py` 扩展）+ runner 单测。
- e2e：起 7009（[[internal-llm-aikit]] 坑：新增 workspace 包必须完整重启 uvicorn，用 `run.sh`）。
- 浏览器：详情页新 tab（关联工具）+ playground 工具 / 子 agent 事件卡片，截图存证（[[implementation-review]]）。
- 真实 LLM 跑通（new-api 网关，[[gateway-newapi-local]]）。
```
