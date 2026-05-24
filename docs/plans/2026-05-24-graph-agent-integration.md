# 工作流即智能体：可视化编排生成可对话 Agent（Dify Chatflow / FastGPT 套路）

状态：设计中（2026-05-24）。目标是让「可视化编排的工作流」成为一种**智能体**，
与 `agents/` 手写智能体统一类型、走同一对外端点，并补上对话式调试。

## 目标 / 非目标

**目标**
- 工作流（graph）可作为一个 Agent 对外暴露，调用方式与现有 agent **完全一致**
  （同一端点 `POST /v1/agents/{key}/invoke`，同一鉴权、会话、计费、对话页可见）。
- 编辑器内提供**对话式调试**（多轮聊天，不必先发布即可调当前 draft）。
- 不破坏现有 local / dify / fastgpt agent 与端点。

**非目标（后续阶段）**
- 跨轮 conversation variables（Dify 那种）—— P4。
- OpenAI 兼容 `/v1/chat/completions` 网关 —— P4（若要对齐 FastGPT 接入）。
- graph agent 调用的完整 trace tree 持久化 —— 先复用 agent 单条 call_log，P4 再深化。

## 背景：我们已具备的两块基础（这是整套设计成立的前提）

1. **统一对外端点 + Provider 抽象**：`POST /v1/agents/{key}/invoke`
   （`chameleon-api/.../agent/`）按 api_key→App→workspace 鉴权，SSE 流式；
   invoke service **已经**做了 session 创建/取、历史加载、user/assistant 消息持久化、
   对话页可见、call_log 计费、流式聚合。它按 `AgentDef.provider` 派发到一个
   `Provider`（`stream()`/`invoke()`）。
2. **Agent 已有 `source` 判别位**（`local`/`dify`/`fastgpt`）+ `config` JSON。

> 结论：新增「工作流智能体」= 新增一种 **Provider（`source='graph'`）**，内部把图引擎
> 跑起来。会话/历史/对话页/流式/计费全部复用 invoke service，**且就是同一端点**。

| | Dify | FastGPT | **Chameleon** |
|---|---|---|---|
| 统一单元 | App(mode) | App(type) | **Agent(source)** |
| 编排存哪 | Workflow 表(FK) | App 内嵌 | **Graph 表 + `agent.graph_id`** |
| 对外端点 | /chat-messages | /v1/chat/completions | **已有 /v1/agents/{key}/invoke** |
| 执行分发 | 按 mode | dispatchWorkFlow | **GraphProvider（新增）** |

## 关键事实（已核实，决定实现方式）

- 图引擎 **session-free**：`Orchestrator(spec).run_streaming(input, ctx)`；LLM 节点
  「无 session → 自开短 session 解析」路由，KB 节点走 `search_kb` 自管会话。
  → GraphProvider **invoke 时不需要 DB session**，只需 spec。
- `input` 经 VariablePool 注入 start 节点（`__graph_input__`）。LLMNode 的
  `memory_window` 直接读 input dict 里的 `history` 字段（`llm_messages.build_messages`）。
  → 把对话历史塞进 input 即可获得多轮记忆，无需改引擎。
- 流式事件 wire：`{"graph.node.delta":{node_id,delta}}` / `graph.node.finished{output}` /
  `graph.finished{status,output,...}`（`engine/event_manager.py`）。
- registry `build_agent_registry_from_db` 按 `row.source` 映射 provider，循环内 session
  仍开着 → 可在此 JOIN 出 graph 的 `published_spec` 塞进 AgentDef.config。

## 设计

### 数据模型
- `Agent` 新增 `graph_id`（nullable BigInteger FK → graphs.id）。alembic 迁移。
- `source` 新增取值 `'graph'`（字段无枚举约束，不需迁移，仅约定）。
- 运行时一律服务图的 **`published_spec`**（决策③）；draft 只在编辑器调试端点跑。

### GraphProvider（新 workspace 包 `chameleon-providers/graph`）
`PROVIDER = GraphProvider()`，`name="graph"`，被 registry namespace 扫描自动注册。
`stream(ctx)`：
1. 取 `spec = ctx.agent_def.config["spec"]`（registry 预载的 published_spec）。
2. 由 ctx 组 graph input：
   - `input: str` → `{"query": input, "history": <ctx.history 映射>}`
   - `input: list[Message]` → 末条 user 为 query，其余为 history
   - history 映射成 `[{"role","content"}]`（取 `.text()`）喂给 LLMNode.memory_window。
3. `NodeContext(request_id=ctx.request_id or 生成, graph_id=config["graph_id"],
   graph_run_id=0, started_at=now, extra=ctx.context_vars)`。
4. `Orchestrator(spec).run_streaming(input, ctx)`，把 graph 事件翻成 StreamEvent：
   - 答案节点的 `graph.node.delta` → `delta{text}`（token 流）。
   - `graph.node.started/finished` → `step{name,status,duration_ms}`（节点进度可见）。
   - `graph.node.failed` / `graph.finished status=failed` → `error`。
   - `graph.finished` → 提取**最终答案文本**（见下）+ `done`。
   `invoke()` 用基类默认（聚合 stream）。

### 答案节点约定（决策②）
- 默认取 **`end` 节点输出**作为答案；某节点 `data.is_answer=true` 时优先它。
- 文本提取：若该输出是 dict 且含 `answer` 键 → 用 `answer`；是 str → 直接用；
  否则 `json.dumps`。token 流 delta 来自该答案节点上游的 LLM 节点（按 spec 预判 node_id）。

### registry 接入
`build_agent_registry_from_db`：session 内额外查 source='graph' 行对应 Graph 的
`published_spec`，对每个 graph agent 置
`config = {"graph_id": row.graph_id, "spec": <published_spec>}`；无 published_spec
（从未发布）→ 跳过 + warn。发布 graph 后调 `reload_agent_registry()` 刷新。

### 编排出 agent（authoring）
图编辑器「发布」时 create/update 一个 graph-backed Agent（`source='graph'`,
`graph_id`, `agent_key` 由 `graph_key` 派生），并 reload registry。

### 对话式调试（编辑器内）
`POST /v1/admin/graphs/{id}/chat/stream`：临时**内存会话**多轮调试**当前 draft**
（前端持 history 客户端管理），复用 GraphProvider 的 input 组装 + 引擎流式逻辑，
不落库、不必发布。前端编辑器右侧聊天面板消费。

### 端点统一
graph-backed agent 与手写 agent 都走 `POST /v1/agents/{key}/invoke` → Provider 派发。
天然统一，无需新对外端点（OpenAI-compat 网关另列 P4）。

## 分期
- **P1（后端核心）**：`Agent.graph_id` 迁移 + `source='graph'` + `chameleon-providers/graph`
  GraphProvider + registry 预载 spec → graph agent 从统一端点跑通（流式 + 多轮）。
- **P2（后端调试）**：`/v1/admin/graphs/{id}/chat/stream` 临时会话调试 draft。
- **P3（前端）**：编辑器聊天调试面板（替/补 RunDialog）+「发布为智能体」+ agents 列表标 graph 来源。
- **P4**：答案节点 UI、conversation variables、trace tree 持久化、OpenAI-compat 网关。

## 风险 / 待定
- 新 workspace 包 `chameleon-providers/graph` 的安装（root pyproject members + uv sync）。
- graph agent 的 call_log/trace：P1 复用 invoke service 单条 call_log；图内节点 trace 树
  暂不持久化（test-run 同款 in-memory），P4 再接 run_graph 持久化路径。
- 答案节点判定的边界（多 end / 无 LLM 终点）：先按约定，UI 可显式标注（P4）。
- registry 刷新时机：发布即 reload；spec 改了不发布不影响线上（符合发布语义）。
