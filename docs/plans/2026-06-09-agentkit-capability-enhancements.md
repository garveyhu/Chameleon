# agentkit 能力增强路线图（对标 2026 主流框架）

> SSOT。基于 2026-06 对主流 agent 框架（LangGraph 0.4 / OpenAI Agents SDK+Temporal / CrewAI 1.x /
> Mastra / Pydantic AI / Claude Agent SDK）的检索 + 对 agentkit 现状的实地核查，规划三梯队增强。
> 供后续 /loop 逐项执行。每项标：为什么 / 外面怎么做 / 我们怎么落（复用现成件）/ 关键文件 / 工作量 / 风险 / 验收。

## 背景：对标结论

agentkit 现状能力很全（ctx 表面 + 四 transport + MCP 双向 + A2A + 沙箱 + OTel 观测 + HITL），
**持平偏前**的维度：MCP 双向互操作、沙箱隔离（多数框架没有）、A2A agent card、OTel semconv 观测。

**明显落后 / 缺口**（本路线图要补的）：

| 维度 | 外面 2026 | agentkit 现状 | 出处 |
|---|---|---|---|
| memory | 语义召回 / working / observational 压缩（行业公认**最大缺口**） | **仅 KV** | `_runtime.py:696 _MemoryProxy` |
| durable 覆盖 | 每个 LLM/工具调用可重试可恢复（OpenAI+Temporal 3 月 GA 跑 Codex） | **仅 complete(文本)+ask_human**，其余 raise | `_runtime.py:349 _durable_guard` |
| guardrails | NeMo（5 类轨）/ Guardrails AI（70+ 校验器）/ LLM Guard / Llama Guard | **无** | — |
| ctx 弹性/重试 | Temporal 式自动重试每次调用 | **ctx 无重试**（只 aikit 有） | `chameleon-aikit/.../base.py _invoke_with_retry` |
| agent eval 闭环 | LangSmith agent evals / step-level 追踪 | 有强 eval 域但**没接 agentkit** | `chameleon-system/.../datasets/` |
| 流式 UI | AG-UI 实时把工具调用+文本流到 UI | 文本流 | 新兴，暂不纳入本期 |

---

## 第一梯队（差异化 + 踩风口）

### T1-1 memory 升级：语义召回 + working + observational（**最高推荐**）

**为什么**：2026 行业公认 memory 是框架间最大缺口（仅 CrewAI/Mastra/Google ADK 有真记忆）。谁做好谁
出彩。对"代码智能体"定位最实用（跨会话记住用户/积累知识）。**且我们有现成向量+rerank 检索栈可复用，
ROI 异常高。**

**外面怎么做**：
- 语义召回（semantic recall）：把记忆 embedding 入向量库，按 query 语义检索相关过往（Mem0/Mastra）。
- working memory：结构化的偏好/事实槽，每轮自动注入上下文（Mastra/CrewAI）。
- observational memory（Mastra 2 月最新颖）：Observer+Reflector 双后台 agent 把旧对话压成稠密观察，
  长对话不爆上下文窗口。
- graph memory：按实体/关系检索（mem0 高级形态，本期可不做）。

**我们怎么落**（三层，复用现成件）：
1. **语义召回**：`ctx.memory.search(query, top_k=)` 新原语。`memory.set(k, v)` 时旁路 embedding 入一个
   按 scope_ref 隔离的向量集合——**复用 `chameleon-engine/.../retrieval/pipeline.py` 的 embedding +
   hybrid + rerank**，不要重造。检索按 scope_ref 过滤（隔离同 dev/session/end_user）。
2. **working memory**：`@agent(working_memory=MySchema)` 声明一个 pydantic 结构；运行时自动 `memory.get`
   该槽并注入 system，agent 可 `memory.update_working(...)` 增量改。落 AgentMemory 一个保留 key。
3. **observational 压缩**：长对话/大记忆触发后台压缩任务（**复用 aikit 任务基建 `chameleon-aikit/tasks/`**
   跑 Observer 抽取 + Reflector 合并），把旧条目替换成稠密观察。异步、不阻塞主调用。

**关键文件**：`chameleon-agentkit/.../_runtime.py`（_MemoryProxy 扩 search/working）、
`chameleon-engine/.../retrieval/pipeline.py`（复用检索）、`chameleon-aikit/tasks/`（压缩任务）、
新迁移（向量集合表 or 复用 KB 的 chunk 表加 scope 维度）。

**工作量**：中-大（3 子片：语义召回 / working / observational）。**风险**：向量集合 scope 隔离要严
（别串号，复用 [[api-key-scope-model]] 的 scope 纪律）；observational 压缩别丢关键事实（可保留原始 + 加
压缩视图，非破坏式替换）。**验收**：跨会话语义召回真命中；working memory 自动注入；长对话上下文窗口稳定。

### T1-2 durable 覆盖扩展

**为什么**：durable execution 是 2026 主线表准（OpenAI+Temporal GA 跑 Codex 日百万级）。我们已起步但
**只做了一半**——`_durable_guard` 对 tools/A2A/RAG/结构化/media/stream 全 raise，"可恢复执行"跑不了真
agentic 活。补齐=追平主线。

**外面怎么做**：把每个 LLM/工具/外部调用当可重试 activity，记录进 journal，重放时返记录值不重执行
（Temporal/LangGraph checkpointer）。LangGraph 短板：只在节点间存、节点内循环丢——我们的 memoization
按 call_index 粒度，理论上更细。

**我们怎么落**（扩 `_memoize` 覆盖，按易→难分片）：
- **易**：`kb.search`（journal 检索结果 list）、`media.generate`（journal 产物 URL，artifact 已在存储）、
  `complete(schema=)`（journal 序列化的 pydantic dict，重放 model_validate 还原）。
- **中**：`call_agent`/`gather`/`route`（journal 子 agent 最终输出，重放直接返；子 run 不重跑）；
  `stream`（journal 累积文本，重放一次性吐）。
- **难**：`run_with_tools`（ReAct 循环内多 LLM+工具步，按循环内 call_index 逐步 journal）。

每放开一类，删 `_durable_guard` 对应分支 + 加重放路径 + 真-DB 测试（参照 `tests/test_durable_hitl_scope.py`
的真库往返 + 幂等模式）。

**关键文件**：`_runtime.py`（_memoize/_durable_guard/各 ctx 方法）、`tests/test_durable_hitl_scope.py`
（测试范式）。**工作量**：大（多片）。**风险**：重放确定性（控制流不能依赖未 journal 状态，已有指纹
校验）；序列化（pydantic/媒体）；run_with_tools 循环内 call_index 对齐。**验收**：durable agent 用
tools/RAG/A2A 跑通暂停-恢复、重放零重复计费。

---

## 第二梯队（上生产硬门槛）

### T2-1 guardrails 层

**为什么**：合规/安全场景准入证。外面生态成熟（NeMo 5 类轨 / Guardrails AI 70+ 校验器 / LLM Guard /
Llama Guard 3），五类风险：幻觉/注入/PII/跑题/毒性。我们**完全没有**。

**外面怎么做**：声明式轨道——input（注入/长度/分类）、output（毒性/PII/schema/相关性）、retrieval、
execution（工具调用前校验）。校验器可组合，失败可拒/改写/重试。

**我们怎么落**：
- 声明式：`@agent(guardrails=[PiiScrub(), NoInjection(), MaxLen(8000), OutputSchema(...)])`。
- 运行时：ctx 在 complete/stream 入口跑 input 轨、出口跑 output 轨；命中按策略（block/redact/retry）。
- 复用：PII 已有基础（`tests/test_datasets_pii.py` 对应实现），moderation 可走一个轻分类模型或正则起步。
- 内置一组（PII/注入/长度/输出 schema），留扩展点接外部（Llama Guard 等）。

**关键文件**：新 `chameleon-agentkit/.../guardrails.py` + `_runtime.py`（ctx 入出口挂钩）+ `_spec.py`
（@agent 加 guardrails 声明）。**工作量**：中。**风险**：别拖慢主路径（轻量校验优先 + 异步重活）；
误杀（策略可配 warn-only）。**验收**：注入/PII 样例被拦/脱敏；output schema 违例可重试。

### T2-2 ctx 弹性 / 重试

**为什么**：一次 429/超时就整个 agent 失败，生产不可靠。Temporal 式每调用自动重试是标配。我们 ctx 层
**没有**（重试只在 aikit 系统任务层）。

**我们怎么落**：把 `chameleon-aikit/.../base.py:_invoke_with_retry` 的重试+退避**下沉/复用**到 agentkit
ctx.complete/stream/run_with_tools——对瞬时错误（rate limit/timeout/5xx）退避重试，非瞬时（4xx/校验）
直接抛。可 `@agent(retries=N)` 配。注意：durable 下重试要与 journal 协调（重试成功才记 journal）。

**关键文件**：`_runtime.py`（complete/stream/run_with_tools）、参考 `chameleon-aikit/.../base.py`。
**工作量**：小-中。**风险**：与 durable journal 交互（重放 vs 重试别冲突）；别重试不该重试的（结构化
解析失败≠瞬时）。**验收**：注入瞬时错误自动恢复；非瞬时不空转。

---

## 第三梯队（便宜的高 ROI）

### T3-1 agent ↔ eval 回归闭环

**为什么**：改 agent 代码无法跑回归/打分=没安全网。我们**有顶级 eval 域**（datasets runner+judges+
对比+优化），却没接 agentkit。接上=改代码能跑数据集回归打分+版本对比，工程量小、价值大。

**我们怎么落**：datasets runner 加一条 `source='agentkit'`（or local agent）执行路径——把数据集样本喂给
agentkit agent（经统一 invoke），收集输出走现有 judge 打分。复用现有运行/裁判/对比/优化全套 UI。

**关键文件**：`chameleon-system/.../datasets/runner.py`（加 agent 执行分支）、`service.py`、前端 eval 域
（应已支持选 agent 作被测对象，核实）。**工作量**：小。**风险**：低（复用现成）。**验收**：选一个 local
agent 对数据集跑出评分 + 版本对比。

---

## 推荐执行顺序

1. **T1-1 memory 升级**（先出细化子方案再动手）——差异化 + 复用检索栈 ROI 最高，单一首推。
2. **T3-1 eval 闭环**——便宜、给后续所有改动加回归安全网，建议早做。
3. **T2-2 ctx 弹性**——小而硬的生产门槛。
4. **T1-2 durable 覆盖**——大工程，分片推进（易→难）。
5. **T2-1 guardrails**——合规场景触发时做。

> 纪律（沿用本仓既有约定）：MVC 严格分层 / Result 包装 / 真-DB 测试不 mock / 改 durable 必补真库往返
> 测试 / 弃用代码直接删 / 每步 ruff+boot+lint-imports / 前端改动 tsc+eslint + 浏览器验证。
> agentkit 分层铁律：不反依赖 engine/system；复用检索走 engine、复用任务走 aikit。

## 来源（2026-06 检索）

- 框架对比：gurusup「Best Multi-Agent Frameworks 2026」、firecrawl「open-source agent frameworks」
- durable：AgentMarketCap「Durable Agent Execution in Production 2026」、AppScale「Temporal+LangGraph」
- memory：mem0「State of AI Agent Memory 2026」、generative.inc「Mastra 2026」（observational memory）
- guardrails：digitalapplied「LLM Guardrails 2026」、ToolHalla「Agent Guardrails & I/O Validation 2026」
- 观测/协议：digitalapplied「Agent Observability 2026」、Zylos「Agent Interoperability Protocols 2026」
