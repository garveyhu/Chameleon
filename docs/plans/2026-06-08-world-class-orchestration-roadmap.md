# Chameleon 世界顶级开源代码编排框架 —— 总路线图

> 状态：战略路线图（SSOT），多智能体共同制定（4 设计 + 1 对抗评审）
> 目标：让 Chameleon 成为「**以代码为核心的智能体编排框架**」的世界顶级开源项目，做代码编排的老大
> 前置：`2026-06-08-agentkit-capability-completion.md`（R0+P0+P1 已交付）
> 关联评估：本路线图基于 4 维度评估（作者体验 4/5、ctx 能力 3/5、平台供给 3.5/5、运维商业 3/5）

---

## 0. 定位楔子（最重要，决定取舍）

**一句话定位**：Chameleon 是「**代码即真相的托管运行时**」——作者只写 `@agent` + `async def handle(ctx)`，平台隐式接管模型池 / KB / 向量 / 会话 / trace / 计费 / A2A / 嵌入式分发。从"写完一行 agent"到"它在生产里有鉴权、有配额、有 trace、能被前端 embed、能被另一个 agent 调用"是**零样板**的。

这是 **LangGraph（要自己拼基建）、OpenAI Agents SDK（要自己接 observability/billing）、Dify（不能写真代码）都没有同时给出的组合**。

**定义"老大"的 3 个特性（资源必须压在这里，不要平均用力追平所有人）：**
1. **配置双源 / 代码优先** —— 代码写死即可跑，web 只是降门槛的托管层。竞品没有这条。
2. **隐式全栈托管 ctx** —— 模型路由 + KB 自动 citation + trace 不断链 + 计费 rollup 全自动收口（`_runtime.py` 已证明抽象成立）。
3. **进程内 A2A + 嵌入式分发** —— 一个 agent 写完即是可被调用的服务、即是可嵌入的前端组件。

> ⚠️ **对抗评审的核心警告**：上一版 4 维度方案是"逐个追平竞品功能"，但**定义品类的三件事——标准互操作（MCP/OTel/开放 A2A）、多语言 authoring、可复现+安全的多租户运行时——几乎全空白**。本路线图据此重排：把 MCP 互操作扶正为 P0 旗舰，OTel 出站 + 统一成本/安全闸提前，把"编码工作区"从旗舰位摘下（让它先被 MCP 外采、且必须在沙箱之后）。

---

## 1. 五大 Track 与现状

| Track | 主题 | 评估分 | 一句话现状 |
|---|---|---|---|
| **T1 标准互操作**（评审新增，最高战略）| MCP / OTel 出站 / 开放 A2A / 流协议 / TS authoring | — | **几乎空白**：工具是私有 Python registry（无 MCP）、trace 是私有 call_logs 单向 ingest（无 exporter）、A2A 私有进程内、TS SDK 仅 tracing 非 authoring |
| **T2 ctx 能力面 / 编排原语** | 多模态/编码工作区/HITL/并行/检索/记忆/长任务 | 3/5 | 对话/RAG/工具/A2A/记忆/结构化顺畅；多模态生成、HITL、编码工作区、长任务缺 |
| **T3 作者体验 / 分发** | 自动发现/脚手架/热重载/测试套件/类型 | 4/5 | 业务代码极少，但"建文件夹"被低估：要手动改 app deps + uv sync + 重启 |
| **T4 生产 / 多租户 / 安全** | 沙箱隔离/版本化/配额/规模化 | 3/5 | 进程内裸跑=信任源码、A2A 预算可被客户端绕过（真实漏洞）、无版本化/配额/隔离 |
| **T5 可观测 / 评测 / 生态** | dev trace/评测闭环/replay/SDK文档/市场 | — | 可观测+评测地基强；dev 本地无 trace（NullSpan）、无 agent 级评测 CLI、无 replay、生态物料缺 |

---

## 2. 路线图总览（修正后的关键路径）

对抗评审重排后的**前 5 件事**（按"成为老大"，非按维度）：

| # | 事项 | Track | 为什么是关键路径 |
|---|---|---|---|
| **1** | **MCP 双向互操作**（client 先行） | T1 | 品类入场券。2025 MCP 是事实工具标准，缺它=用户工具生态为零、agent 进不了别人 IDE。比"自造编码工作区"更优先（工具生态 > 自造工具）|
| **2** | **统一成本/安全闸**（ReAct 循环 + A2A + 工具 贯穿 token 预算 + 修预算注入漏洞）| T4 | 多租户/开源平台的钱与安全底线；现存 A2A 预算可被客户端绕过是真实可利用漏洞，必须最先堵 |
| **3** | **作者体验放大**（自动发现去手动 deps + `agentkit new` + dev 闭环）| T3 | 直接放大"代码即真相"楔子，外部开发者第一接触点 |
| **4** | **OTel 出站 exporter**（GenAI semconv 对齐）| T1 | 解除 trace 锁定，让有可观测栈（LangSmith/Langfuse/Arize）的团队敢用。低工程量（已有 ingest 半套）高战略回报 |
| **5** | **不可信沙箱 SandboxTransport**（受控 RPC 隔离）| T4 | 开源=任何人可提交 agent 代码，"靠 PR review 兜"不成立，第一个恶意 PR 就是 RCE。是"接受外部 agent"承诺的前提 |

**建议砍 / 推后**：编码工作区 `ctx.fs/shell`（从旗舰摘下，先用 MCP 外采 fs/shell server，且必须在沙箱之后）、向量记忆 recall（kv 够 MVP）、agent 市场 / benchmark（有外部用户后再做）、AG-UI 标准化（等第三方前端集成需求）。

---

## 3. T1 — 标准互操作（评审扶正为最高战略，原方案盲区）

### T1-1 MCP 双向互操作 🔴🔴 P0 旗舰

**现状**：`grep mcp` 全 backend 零命中；工具只能进私有 `integrations/tools/registry.py`（`register_tool` Python 类）。

**做法（双向）**：
- **MCP client**（先行）：`@agent(mcp_servers=[...])` 或 `ctx.mcp` —— 启动期连外部 MCP server，把其 tools 适配成现有 `Tool` 协议进 `run_with_tools` 循环、resources 适配成 `ctx.kb`/上下文。复用 `integrations/tools` 的 loop/execute 原语，新增 `integrations/mcp/client.py`（MCP stdio/SSE/HTTP transport）+ 把 MCP tool schema 映射成 `tool_schemas`。
- **MCP server**：把已注册 agent + 平台工具自动暴露成一个 MCP server endpoint（`/mcp`），让 Chameleon agent/工具能被 Cursor/Claude/别的客户端消费。
- **协议接缝**：在 `Tool` 协议与 `run_tool` 之间插入适配层，私有 registry 与 MCP 工具统一走同一循环。

**为什么 P0**：工具生态 > 自造工具。缺 MCP 直接出局。
**ROI**：极高 / **工作量**：L（client 先，server 后）。
**验收**：`@agent(mcp_servers=["filesystem","github"])` 能在 ReAct 循环里调外部 MCP 工具；Chameleon agent 能被 Claude Desktop 当 MCP server 调。

### T1-2 OpenTelemetry GenAI semconv 出站 🔴 P0

**现状**：`api/otel/` 仅 ingest（收 OTLP 进 call_logs），**无 exporter**；span 属性是私有 `chameleon.observation_type`。

**做法**：① OTLP exporter 把 call_logs 按 GenAI semconv 导出到用户配置的 LangSmith/Langfuse/Arize/Phoenix；② span 属性对齐 `gen_ai.*` 标准命名（私有命名保留内部用，导出时映射）。复用现有 `observe/sink` + `aggregate_generation_rollup`。

**为什么**：trace 不再是单向黑洞，解除锁定恐惧（顶级框架卖点=接你现有 observability）。
**ROI**：高 / **工作量**：M。

### T1-3 开放 A2A 协议适配 🟠 P1

**现状**：`engine/agent/a2a.py` 是私有进程内注册表（硬编码 `MAX_DEPTH=3`、进程内 `AGENTS`）。

**做法**：A2A-over-HTTP 适配器——agent 暴露成 Google A2A server + `ctx.call_agent` 能指向远程 A2A URL。内部私有协议保留做进程内快路径。
**ROI**：中 / **工作量**：M（MCP 之后）。

### T1-4 TS authoring SDK —— 战略决策题 🟠 P1（定位）/ P2（实施）

**现状澄清**：`sdk/typescript/` 存在但是 **tracing-only client**（`ChameleonClient.withTrace/withSpan`），**没有 `@agent`/`ctx` authoring 能力**。authoring 只有 Python。

**决策**：要么明确"Python-first authoring，TS 仅 tracing/client"并接受不争 TS authoring 市场；要么把 TS authoring 当独立大版本立项（需第二套 Node runner + transport，巨大投入）。**红线：别让 README/营销暗示 TS 能 author。**
**建议**：发布期 Python-first，诚实标注；TS authoring 列入未来大版本。

### T1-5 流协议标准化（AG-UI）🟡 P2

私有 `StreamEventType` 能用；等有第三方前端集成需求时做一层 AG-UI / OpenAI streaming delta 适配层，不动内核。

---

## 4. T2 — ctx 能力面 / 编排原语

> 设计原则：复用引擎设施不重造、配置双源、公共面只增不改、engine 能力经 IoC 桥注入（仿 a2a_bridge）、trace 不断链（`_scoped_observation_id`）。

### T2-1 `ctx.kb.search` 接 hybrid + rerank + 查询扩展 🔴 P0（小改大收益）
**现状**：走旧 `search_kb`（单库纯向量），`engine/retrieval/pipeline.py` 的 hybrid+RRF+multi-query+HyDE+rerank 没接进来。
**做法**：新建 `providers-base/retrieval_bridge.py`（IoC 桥）+ engine `wire_retrieval_bridge()`（app 注入）；`KbHandle.search` 增可选 `mode="hybrid"/rerank/expand/hyde`（默认升级 hybrid）；桥未注入回退现路径。
**ROI**：极高 / **工作量**：小。

### T2-2 多模态生成入口 `ctx.media` 🔴 P0（小改大收益）
**现状**：平台 `mediagen/service.stream_generate`（ComfyUI+DashScope 图/视频）完整，`ctx` 零入口。
**做法**：`ctx.media.generate(kind, prompt, *, slot/model, params, input_images)` → transport 解析 slot/model→model_id→`resolve_media_target`→`stream_generate`，进度自动 emit step、产物落 MinIO 自动 emit + usage。补 code→id 解析。
**ROI**：高 / **工作量**：小（mediagen 全有）。

### T2-3 工具循环升级（并行 + token 预算 + 流式 + 重试）🟠 P0（并入统一成本闸 T4-1）
**现状**：`run_tool_calls` 串行、只 `max_steps`、无 token 预算。
**做法**：`integrations/tools/loop.py` 加 `run_tool_calls_parallel`（`asyncio.gather` 保序）+ 单工具重试；`run_with_tools` 增 `parallel`/`max_tokens`（循环级预算，与 A2A 预算同源）。
**ROI**：中 / **工作量**：中。

### T2-4 HITL：`ctx.ask_human` + `require_approval` + guardrails 🟠 P1
**现状**：engine `human_input` 暂停-恢复完整，ctx 无 ask_human；`ObservationType.guardrail` 枚举留了没实现。
**做法**：MVP 同步审批（`run_with_tools(require_approval=[...])` 当轮等待）+ `ctx.guardrail(input/output check)`；完整档 `ctx.ask_human` 抛 `AgentPaused` → 落库 + checkpoint → 回填重放（依赖 T2-6 + T4 checkpoint）。复用 `human_input_pending` 表 + 前端人审表单。
**ROI**：高 / **工作量**：大（完整档依赖 checkpoint）。

### T2-5 A2A 升级：结构化返回 + 并行扇出 + handoff 🟠 P1
`ctx.call_agent(schema=)` 结构化返回 + `ctx.gather_agents([...])` 并行扇出 + `ctx.handoff(target)` 转移控制权（OpenAI Agents 语义）。复用 a2a_bridge（扩 `_caller` 返回结构化 + usage）。
**ROI**：中 / **工作量**：中。

### T2-6 向量记忆 + 结构化流式 + embedding/rerank slot 🟢 P1
`ctx.memory.recall(query)` 向量召回（复用 pgvector + embedding，scope_ref 隔离）；`ctx.stream_structured(schema=)` partial 增量；embedding/rerank slot 运行层支持（transport 按 kind 分派 factory）。
**ROI**：中低 / **工作量**：小-中。

### T2-7 编码工作区 `ctx.fs/shell/code` —— ⚠️ 从旗舰摘下，推后 + 沙箱后置
**评审判定**：这是最像"自造轮子"的一项（追平 Claude Code/Cursor harness），对托管楔子是负担，且 fs/shell 直接放大不可信沙箱攻击面。
**修正策略**：① 先用 MCP（T1-1）外采现成 fs/shell MCP server，把工作区做成 MCP 能力而非内核；② 若要内核级 `ctx.fs/shell/code`（有状态 workspace + `SandboxSession` 协议 + docker 长驻卷 + MinIO 快照），**必须在 T4 沙箱之后**，绝不先于沙箱（没沙箱的 fs/shell 是裸奔）。
**ROI**：高战略但风险高 / **工作量**：大 / **优先级**：P1-P2，沙箱后置。

### T2-8 长任务 / 可恢复 `ctx.checkpoint` / `ctx.step` 🔴 战略地基 P1
**现状**：graph 有 `seed_outputs` resume + `graph_runs` 锚，agentkit 完全没接。评审强调"确定性/可复现是调试+评测+事故复盘地基，不是锦上添花"。
**做法**：新建 `agent_runs` durable 表（status/step_outputs/workspace_snapshot/scope_ref）；`ctx.step(name, coro)` checkpoint 单步，崩溃/暂停后重放已完成 step（照搬 orchestrator `seed_outputs` 语义）。是 T2-4 完整 HITL + T2-7 workspace 快照的共同地基，统一设计。
**ROI**：战略地基 / **工作量**：大。

---

## 5. T3 — 作者体验 / 分发

### T3-1 自动发现 workspace member，废掉手改 app deps 🔴 P0（杀最大痛点）
**现状**：每个 agent 必须手动加进 `chameleon-app/pyproject.toml` 的 dependencies + sources 才进 venv 才被 namespace 发现。
**做法**：`registry.py` 新增 `_augment_agents_namespace_path()`，dev 态把 `chameleon-agents/*/src` 注入 `chameleon.agents` 命名空间 `__path__`（`CHAMELEON_AGENTS_ROOT` env，`run.sh` 设），源码进目录即被发现，无需声明依赖；生产走标准 pip 安装。移除 example 在 app deps 的声明。
**ROI**：极高 / **工作量**：M。

### T3-2 `agentkit new <name>` 脚手架 🔴 P0
一条命令出完整可跑包（pyproject/__init__/agent.py/tests 全填好），模板从 examples 参数化（单一来源）。`--template rag/tool/chat/class/a2a`。
**ROI**：极高 / **工作量**：M。

### T3-3 作者测试套件 `FakeTransport` + `agentkit test` 🔴 P0
提炼公共 `chameleon.agentkit.testing`（`FakeTransport`(RuntimeTransport 第三实现) + `make_run` + `collect`），让作者离线写确定性单测（对标 Pydantic AI `TestModel`）。脚手架自动生成示例单测。
**ROI**：极高（外部开发者刚需）/ **工作量**：M。

### T3-4 `agentkit dev` 一键本地环境 + 热重载 🟠 P1
一条命令：预检 dev token → chat REPL → watch 文件改动热 reload（需 `_unregister(key)` 解决重复登记）。复用 HttpDevTransport + `/v1/dev/ping`。
**ROI**：高 / **工作量**：M。

### T3-5 作者面打磨（4 项小改）🟠 P0-P1
- **类式元数据单一真相源**：`@agent` 装饰类自动合成 `get_metadata()`（删重复声明 + 防漂移）。P0 小改。
- **`ctx.config` 运行时注入 `Opt.default`**：runner 铺默认值，作者不再 `or default` 双写。P0 小改。
- **`ctx.wrap(model)` 实现或撤销**：兑现设计文档逃生口承诺（自带 LangChain model，绕路由/计费但走 span）。P0 小改。
- **强类型 ctx**：`complete(schema=T)->T`（overload）、`@agent`/`@tool` 保签名（ParamSpec）。P1。

### T3-6 公共 API 冻结门禁 + 外部 pip 化 🟠 P1
`api-snapshot.json` 机器化护栏（删/改签名 CI 红，只增允许）；agentkit 对 core/providers-base 只用类型（可抽零依赖类型包）使 `pip install chameleon-agentkit` 独立可用 + semver + CHANGELOG。
**ROI**：中 / **工作量**：M。

---

## 6. T4 — 生产 / 多租户 / 安全

> 信任分级模型（落 `Agent.trust_tier`）：`platform`（内建/审核过，进程内零开销）/ `internal`（可信，默认进程内可强制沙箱）/ `untrusted`（第三方，**强制沙箱 + 受控 RPC + 拿不到 DB/网络/env/密钥**）。

### T4-1 修 A2A 预算客户端绕过漏洞 + 统一成本闸 🔴🔴 P0（真实漏洞，最先做）
**漏洞**：外部可控 `req.context` 被 `**req.context` 原样 spread 进 `context_vars`（service.py:332），runner 从中读 `_a2a_budget`/`_a2a_depth`，调用方塞 `_a2a_budget: 999999999` 即绕过红线；invoke 入口不设初始预算。
**修复（三层纵深）**：① 入口 `_sanitize_context` 剥所有 `_` 前缀保留键（常量集中 providers-base）；② `resolve_initial_budget(app, agent)` 服务端按 key 配额权威下发 `_a2a_budget`；③ a2a.py 透传链同样 sanitize。**并把 token 预算贯穿 ReAct 循环 + A2A + 工具调用统一成本闸**（接 T2-3）。
**ROI**：极高 / **工作量**：1.5 人日（漏洞）+ 中（统一闸）。

### T4-2 SandboxTransport：不可信代码受控 RPC 隔离 🔴 P0（开源承诺前提）
**现状**：`@agent(sandboxed=True)` 只打 warning 不真隔离，agent 主进程裸跑。`SandboxRuntime` 协议 + docker runtime + `HttpDevTransport`（现成 RPC 蓝本）地基全在。
**做法**：`untrusted` 档的 handle 跑容器内（network=none），ctx 资源调用经 **run-scoped 一次性 token** 的受控 RPC 回主进程（鉴权复用 `assert_scope` + 配额闸），白名单动词（chat/kb/tool/memory/call_agent）。`_resolve_sandbox_policy` 从日志桩改真路由：untrusted 沙箱不可用即**拒绝运行**（不再假装隔离）。同一份代码两种跑法（InProcess/Sandbox 同实现 RuntimeTransport）。
**评审定性**："靠 PR review 兜"在开源场景不成立，第一个恶意 PR=RCE。这是**上线前 P0 不是 P1**。
**ROI**：极高 / **工作量**：8-12 人日（先 per-run 非流式，再长驻+流式）。

### T4-3 Agent 版本化 / 灰度 / 回滚 🟠 P1
`agent_versions` 表（版本快照 + code_digest + config/binding 快照）；改代码产 draft 版本而非覆盖；`promote`/`canary_pct`/`options.version`/一键回滚。对标 LangGraph assistant versioning + Temporal worker versioning。
**ROI**：高 / **工作量**：5-6 人日。

### T4-4 配额硬闸 + 余额扣减 🟠 P1
`ApiKey` 已有 `qpm_limit/qpd_limit` 字段但不 enforce；加 `token_quota/balance`，Redis 滑窗限流（复用 rate_limit.py）+ 调用后从 rollup 扣减，超限 429。给 T4-1 的 `resolve_initial_budget` 喂真配额。
**ROI**：高 / **工作量**：5 人日。

### T4-5 规模化运行时（懒加载 + 坏 agent 隔离 + 热注册）🟠 P1
去 fail-fast 单点（坏 agent 标记跳过不拖垮启动）；懒加载（注册期只扫 manifest，首调再 import）；热注册（提交不重启）。
**ROI**：高 / **工作量**：4-5 人日。

### T4-6 分发自动化 + dev token 作用域化 + 生产 checklist 🟠 P1-P2
agent 包上传/git pull 落 `agent_store/` 不污染 app deps（依赖 T4-2 沙箱接 untrusted）；`dev_tokens` 表（作用域+过期+审计）替代单静态 token；生产启动 preflight 强制断言（untrusted 无沙箱即拒启）。
**ROI**：中高 / **工作量**：中。

---

## 7. T5 — 可观测 / 评测 / 调试 / 生态

> 评估共识：可观测+评测**地基强**（trace 树/rollup/dataset/judge/compare/Score/marketplace 全有），70% 工作是"接通已有"。

### T5-1 dev trace 补全（杀 NullSpan）🔴 P0
**现状**：`HttpDevTransport.span()` 返 `_NullSpan`，dev 本地看不到 trace。
**做法**：`/v1/dev/trace` 端点（dev token 闸内落 call_logs）；`_DevSpan` 镜像 `_scoped_observation_id` 累 span+usage，CLI 退出本轮渲染 ASCII trace 树 + web 链接。`/v1/dev/*` 入口包 `open_trace_scope(channel='dev')`。
**ROI**：高 / **工作量**：M（3-4 天）。

### T5-2 `agentkit eval` 回归闭环 🔴 P0（ROI/工作量比最高）
**现状**：`datasets/runner.run_dataset` 已支持 `agent_key` 被测 + `compare_runs`，几乎纯黏合。
**做法**：`agentkit eval <agent> --dataset <k> [--against last]` → `/v1/dev/eval/run` 触发站内 run_dataset → 出分 + GSB 胜率 diff；web 加 agent 回归时间线（复用 run-compare-matrix）。
**ROI**：高 / **工作量**：M（4-5 天）。

### T5-3 Time-travel / replay / fork 🟠 P1
**现状**：仅 graph 有 resume 锚，无 trace 重放。
**做法**：`system/replay/`（input-replay + override，非状态快照恢复，对标 LangSmith "open in playground"）；`POST /v1/admin/traces/{id}/{replay,fork}`（fork=replay+落 dataset）；前端 trace-drawer 加重放 + 并排 diff。打 `channel='replay'` 成本可过滤。
**ROI**：高 / **工作量**：L（5-7 天）。

### T5-4 dev transport 补全 structured/memory/call_agent 🟠 P1
补 `/v1/dev/{llm/structured,memory,call-agent}` 端点，让"两跑法一致"对这三个 P1 能力也成立（现在 dev 全 NotImplementedError）。
**ROI**：中 / **工作量**：M。

### T5-5 SDK 自动文档 + cookbook + 冻结门禁 🟠 P1
`griffe`/`pdoc` 从公共面抽 docstring 生成 API 文档挂 docsify；`api-snapshot.json` 门禁（同 T3-6）；`docs/sdk/cookbook/` 分主题示例（每篇配可跑 example 包）；agentkit 进 1.0.0 + CHANGELOG + `uv build` wheel。
**ROI**：高 / **工作量**：M。

### T5-6 annotation / feedback 回流 🟠 P1
`annotation_queue` 表（低分/👎 自动入队 → 人工打分 Score source=annotation → `sample_from_logs` 落 dataset → 喂优化器）。对标 LangSmith annotation queue。复用 Score + sample_from_logs。
**ROI**：中高 / **工作量**：M。

### T5-7 开源生态物料 🔴 P0（零代码门面，对外必备）
仓库根 `CONTRIBUTING.md` / `LICENSE`（与用户确认协议，建议 Apache-2.0）/ `CODE_OF_CONDUCT.md` / `CHANGELOG.md`（回填 v1.0/v1.1）/ `.github` issue·PR 模板。
**ROI**：中（对外门面）/ **工作量**：S（1-2 天）。

### T5-8 agent 市场 + benchmark 套件 🟡 P2（有外部用户后）
marketplace 从 plugin 扩到 agent（`type='agent'` bundle + `agentkit publish` + 验签 + 安装权限确认，依赖 T4-2 沙箱）；`benchmarks/`（text2sql/RAG/工具/bug-fix 标准任务集，可复现对标证据 + 接 eval_jobs cron 日跑回归）。
**ROI**：中 / **工作量**：L+M。

---

## 8. 致命风险（评审，含不可逆债务）

1. **私有协议锁死（最致命，不可逆）**：A2A 私有进程内、trace 私有 call_logs 单向、流私有 StreamEvent、工具私有 Python registry——四面全私有且越做越深。若 T2 所有原语继续按私有协议盖楼，等用户量起来再补标准层时内核已被私有假设固化，重构成本指数级。**对策**：现在就在工具/A2A/trace 三处插"协议适配层接缝"，标准实现可后置但别让私有假设渗进内核签名。这是 T1 必须与 T2 同步推进的根本原因。
2. **多租户安全是上线前 P0 不是 P1**：开源=任何人可提交 agent 代码，"靠 PR review 兜"不成立。沙箱（T4-2）+ 预算硬闸（T4-1）必须在"接受外部 agent"承诺兑现前落地。
3. **TS authoring 定位自我矛盾**：别让营销暗示 TS 能 author（实际只有 tracing）。诚实 Python-first 或独立大版本立项。

---

## 9. 分期与里程碑（修正排序）

### P0 —— 入场券 + 安全底线 + 楔子放大（发布前必做）
- **T1-1 MCP client**（旗舰）· **T4-1 预算漏洞修复 + 统一成本闸** · **T4-2 SandboxTransport（per-run 非流式先行）**
- **T3-1 自动发现** · **T3-2 `agentkit new`** · **T3-3 FakeTransport 测试套件** · T3-5 作者面 4 小改
- **T2-1 kb hybrid+rerank** · **T2-2 ctx.media** （小改大收益）
- **T1-2 OTel 出站** · **T5-1 dev trace** · **T5-2 `agentkit eval`** · **T5-7 生态物料（LICENSE/CONTRIBUTING）**

### P1 —— 编排原语 + 生产化 + 开发者闭环
- T1-1 MCP server · T1-3 开放 A2A · T1-4 TS 定位决策
- T2-3 工具循环升级 · T2-4 HITL · T2-5 A2A 扇出/handoff · T2-8 checkpoint/长任务（地基）
- T4-3 版本化 · T4-4 配额 · T4-5 规模化 · T4-6 分发自动化/dev token
- T3-4 `agentkit dev` · T3-6 API 冻结门禁/pip 化
- T5-3 replay · T5-4 dev transport 补全 · T5-5 SDK 文档/cookbook · T5-6 annotation 回流

### P2 —— 编码工作区（沙箱后）+ 生态规模化
- T2-6 向量记忆/结构化流式 · **T2-7 编码工作区（沙箱后置，或 MCP 外采）**
- T1-5 AG-UI · T5-8 agent 市场 + benchmark · 社区物料/demo · T2-5 TS authoring 实施（如立项）

---

## 10. 一句话总结

**把 ctx 能力做到与竞品功能对等只是 60 分；定义品类的是标准互操作（MCP/OTel/开放A2A）、可复现+安全的多租户运行时、与"代码即真相托管"楔子的极致打磨。** 把 MCP 双向扶正为 P0 旗舰、OTel 出站 + 统一成本/安全闸提前、编码工作区从旗舰摘下并后置于沙箱——这条修正路径才配得上"世界顶级开源代码编排框架"，而非"功能齐全的内部平台"。

---

## 11. 真 LLM 端到端实跑验证（评审11 钦点的最后门槛已闭合）

用户解锁线上通义千问 key（平台已注册模型）后，经平台 `/v1/dev/call_agent`（dev token 鉴权）
用**真 Qwen 模型**端到端实跑，三大旗舰能力全通过、可观测全真：

- ✅ **基础对话**（qwen-chat）：真 Qwen 出真答案。
- ✅ **工具循环 ReAct**（example-tool-use）：真 Qwen 出 tool_calls → 框架执行 → `(123+456)×7 = 4053`（正确）。
- ✅ **A2A 编排**（example-orchestrator）：真 Qwen 委托子 agent → `99×99 = 9801`（正确）。
- ✅ **可观测/计费**：call_logs 真 generation span（model=qwen-plus）+ 真 token（275~429）+ 真 cost（~$0.0003/次）+ success。

至此"陌生人能跑通 + 真 LLM 出真结果"的真实运行证据**已具备**（此前受本地 LLM 不可达阻塞）。
框架从"全面验证的强候选（7.0）"推进到"真实运行验证通过"——剩余距顶级的差距是**外部真实
采用规模**（社区 star/PR/生产案例），属时间 + 运营，非技术。
