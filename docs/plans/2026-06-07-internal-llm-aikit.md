# 系统内部 LLM 能力收口：chameleon-aikit

> SSOT。状态：方案已定（方向 = 新建 aikit 薄包；范围 = 全量收口），待按批次落地。
> 决策人：用户。日期：2026-06-07。

## 1. 背景与决策

系统里除了"用户经网关/智能体主动调模型"之外，**系统自己内部也在多处调 LLM 来丰富功能**
（评测 judge、知识库检索改写、工作流生成、prompt 优化……）。这些调用散落在
`chameleon-system` 和 `chameleon-engine` 各域的 service 里，各自手写
`get_llm + ainvoke + 容错`，没有一个集中维护的地方。

用户诉求：**把"用到大模型能力"的代码单独用一个模块统一维护**。

已确认决策（两道选择）：

| 决策点 | 选择 |
|--------|------|
| 架构方向 | **新建 `chameleon-aikit` 薄包**（对内 AI 任务库），**不**套 `agentkit` 智能体框架 |
| 收口范围 | **全量收口**（所有内部 LLM 调用点的执行截面统一经 aikit） |

### 为什么不套 agentkit（@agent / AgentRun）

`agentkit` 是为**对外可调用、会话式、流式、可注册成 app** 的智能体设计的运行时
（`AgentRun` / `Provider.stream` / `StreamEvent` / `session` / `ModelSlot` / KB 绑定）。
而内部功能绝大多数是**一次性、结构化输入输出**：judge 要 `(expected, actual, criteria)→score`、
HyDE 要 `query→text`、扩样要 `seeds→candidates[]`。把它们塞进 `query: str` + `yield delta`
的智能体壳子里 = 压扁结构化契约、丢类型、为一次调用装 `InvokeContext` 走 provider 流——纯仪式开销。

「复用 trace/计费」也不成立：见 §3，这些调用**已经**有 trace 在记账，不需要借 agentkit。

二分清晰：**`agentkit` = 对外智能体运行时；`aikit` = 对内 AI 任务库**。两者都站在
`LLMFactory` + trace 切面之上，但面向完全不同的消费者。

## 2. 现状盘点：全量内部 LLM 调用点

| # | 功能 | 位置 | 现状 channel | 收口归类 |
|---|------|------|--------------|----------|
| 1 | LLM judge / llm_score / gsb | `system/datasets/runner.py` `_run_llm_judge`/`_ainvoke_llm` + `judges.py`(prompt/parse 纯函数) | eval | 业务特化 |
| 2 | DSL NL 规则评分 | `system/datasets/dsl/evaluator.py` `_score_nl_rules` | eval | 业务特化 |
| 3 | AI 扩样（流式生成候选） | `system/datasets/ai_generate.py` `ai_generate_stream` | eval | 业务特化 |
| 4 | 单条候选优化/再生成 | `system/datasets/ai_generate.py` `refine_candidate` | eval | 业务特化 |
| 5 | 运行级 Prompt 优化 | `system/datasets/optimizer.py` `_llm_optimize` | eval | 业务特化 |
| 6 | NL→GraphSpec 工作流生成 | `system/graphs/generator.py` `generate_graph_spec` | 无 | 业务特化 |
| 7 | 追问建议生成 | `system/graphs/generator.py` `suggest_followups` | 无 | 通用 |
| 8 | System Prompt 改写 | `system/playground/service.py` `rewrite_prompt` | eval | 业务特化 |
| 9 | 意图分类节点 | `engine/graph/nodes/classifier.py` `ClassifierNode.execute` | 无 | 通用 |
| 10 | multi-query 改写 | `engine/retrieval/expander.py` `expand_queries` + pipeline `default_complete_fn` | 无 | 通用 |
| 11 | HyDE 假设答案 | `engine/retrieval/expander.py` `hyde_query` | 无 | 通用 |

### 明确排除（不属于"系统内部用 LLM 丰富功能"）

| 项 | 位置 | 排除理由 |
|----|------|----------|
| `LLMNode` | `engine/graph/nodes/llm.py` | 这是**用户在工作流里编排的 LLM 节点**，是产品功能本身，不是系统内部偷偷调 LLM。仍走 LLMFactory，不收口。 |
| `stream_test` | `system/models/test_service.py` | 模型连通性探活，是运维/管理动作，不是"丰富业务功能"。保持原样。 |

## 3. 核心洞察：散的是「执行截面」，不是「业务语义」

整个 trace 体系已经很干净：

```
open_trace_scope(TraceContext(channel="eval", request_id=..., ...))   # 入口开 scope（ContextVar）
  └── LLMFactory.create(name).ainvoke([...])                          # client 烧进了 GenerationRecorder 回调
        └── on_llm_end → 自动写一条 generation call_log               # 归属字段从 ContextVar 的 TraceContext 取
```

- `TraceContext` / `open_trace_scope` 在 `chameleon-core/observe/context.py`
- `GenerationRecorder`（烧进每个 cache LLM 实例）在 `chameleon-integrations/observe`
- 没开 scope 时兜底 `channel="internal"` 独立行

**结论**：「统一 trace/计费」不需要任何新框架——只要在 scope 内用 LLMFactory 的 client 调用即可。
真正重复散落的是这截**执行代码**：`get_llm(name) → ainvoke([HumanMessage(...)]) → 取 .content → try/except 容错`，
在 11 处各写一遍。而**业务语义（prompt 构造 + 结果解析）很多已经是纯函数**——
`judges.py` 头部明确写「绝不 import LLM/integrations，守分层纯逻辑」。

所以 aikit 要收口的是**执行截面 + trace 归属 + 重试容错**，不是去搬各域的业务 prompt。

## 4. aikit 职责边界（三件事）

1. **执行层**：`LLMRunner` / `LLMTask` 基类——统一拿 client（按 slot/model_code）、
   `ainvoke`/`astream`、重试、容错降级、在正确 channel 的 trace scope 内执行。
   **消除 11 处重复的 `get_llm + ainvoke + try/except`。**
2. **通用任务库**：无业务语义的通用能力（分类 / 改写 / HyDE / 摘要 / 追问建议）
   **完整进 aikit**（prompt + parse + 执行一体），各域直接调，可跨域复用。
3. **注册表**：`registry.py` 登记**所有**内部 LLM 用法（含 prompt 留在域内的业务特化项），
   `TaskSpec{key, title, domain, channel, location}`——满足「一个地方看全系统在哪用了 LLM」。

### 收口规则（按归类两种处理，统一经执行器）

- **通用项（#7/#9/#10/#11）**：prompt + parse + 执行整体搬进 `aikit/tasks/*`，旧处删除改为调 aikit。
- **业务特化项（#1~6/#8）**：带强域语义的 prompt/parse **纯函数留在域内**（如 `judges.py` 不动，
  保评测域内聚），但**执行截面统一改走 `aikit` 执行器**（替掉各自的 `_ainvoke_llm`/`get_llm+ainvoke`），
  并在 `registry.py` 登记一条 TaskSpec。
- **分层红线**：aikit 不得 import `engine`/`system`。业务特化任务的输出用 aikit 通用结构
  （如 `TextResult` / dict），由域内适配回自己的契约（`JudgeResult`/`GraphSpec`）。
  aikit 负责「把 LLM 调出结构化结果」，域负责「把结果接进业务契约」。

## 5. 包结构与分层

```
backend/chameleon-aikit/
├── pyproject.toml                # name=chameleon-aikit；deps: chameleon-core, chameleon-integrations, langchain-core
└── src/chameleon/aikit/
    ├── __init__.py               # 导出 LLMTask, LLMRunner, run_text, run_stream, register, TaskSpec
    ├── base.py                   # LLMRunner + LLMTask 执行基类（client/调用/重试/容错/trace channel）
    ├── registry.py               # INTERNAL_LLM_TASKS 注册表 + TaskSpec + register()
    └── tasks/
        ├── __init__.py
        ├── classify.py           # 通用：意图分类（#9）
        ├── rewrite.py            # 通用：query 改写 / HyDE（#10/#11）
        └── suggest.py            # 通用：追问建议（#7）
```

业务特化项不在 aikit 建任务文件，只在 `registry.py` 登记 + 域内改调执行器。

### 分层（import-linter layers）

在 `engine` 与 `integrations` 之间插入 `aikit`：

```
chameleon.engine  →  chameleon.aikit  →  chameleon.integrations  →  chameleon.data  →  chameleon.core
```

`root pyproject.toml` 的 `[tool.importlinter]`：
- `root_packages` 增加 `chameleon.aikit`
- 「分层基座单向」契约 layers 列表插入 `chameleon.aikit`（在 engine 下、integrations 上）

`engine`（classifier/retrieval）和 `system`（评测/playground/graphs）都依赖 aikit；aikit 只依赖 core+integrations。零反向。

## 6. 执行基类设计

```python
# aikit/base.py（要点，非最终代码）
DEFAULT_CHANNEL = "internal"

class LLMRunner:
    """内部 LLM 调用的统一执行器：拿 client + 调用 + 重试容错 + trace channel scope。"""

    @staticmethod
    async def run_text(
        prompt: str | list[Message],
        *,
        model: str | None = None,         # model_code；None 走默认
        channel: str = DEFAULT_CHANNEL,   # 不在已有 scope 内时自开；已在 scope 内则复用不覆盖
        system: str | None = None,
        retries: int = 1,
        fallback: str | None = None,      # 全失败返回的兜底文本；None 则 raise
    ) -> str: ...

    @staticmethod
    async def run_stream(...) -> AsyncIterator[str]: ...   # 给 #3 扩样流式用

class LLMTask:
    """通用任务基类：子类声明 key/channel + build_prompt() + parse()。"""
    key: str
    channel: str = DEFAULT_CHANNEL
    def build_prompt(self, **inputs) -> str | list[Message]: ...
    def parse(self, raw: str): ...
    async def run(self, **inputs):
        raw = await LLMRunner.run_text(self.build_prompt(**inputs), channel=self.channel)
        return self.parse(raw)
```

trace 复用语义关键点：`run_text` 若检测到 `current_trace_context()` 已存在（如评测 runner
已在 `channel="eval"` scope 内），**不覆盖**，沿用外层归属；只有裸调用（如 KB ingest 那种无 scope）
才自开 `channel="internal"` scope。这样既不破坏现有 eval 计费归属，又给无 scope 的散调用补上记账。

## 7. 迁移映射表

| # | from | to | 处理 |
|---|------|----|------|
| 9 | `classifier.py` 自调 `resolve_llm`+ainvoke | `aikit/tasks/classify.py::ClassifyTask` | 通用整体迁，节点改调 task |
| 10/11 | `expander.py` + pipeline `default_complete_fn` | `aikit/tasks/rewrite.py`（multi_query/hyde） | 通用整体迁，pipeline 注入改为 aikit 执行器 |
| 7 | `generator.py::suggest_followups` | `aikit/tasks/suggest.py` | 通用整体迁 |
| 1 | `runner._ainvoke_llm` | `LLMRunner.run_text`；`judges.py` 纯函数不动 | 执行截面替换 + 登记 |
| 2 | `dsl/evaluator._score_nl_rules` 注入 llm | 改注入/调用 `LLMRunner.run_text` | 执行截面替换 + 登记 |
| 3/4 | `ai_generate.py` astream/ainvoke | `LLMRunner.run_stream`/`run_text` | 执行截面替换 + 登记 |
| 5 | `optimizer._llm_optimize` | `LLMRunner.run_text` | 执行截面替换 + 登记 |
| 6 | `generator.generate_graph_spec` | `LLMRunner.run_text`（两轮重试用 retries）；GraphSpec 校验留 engine | 执行截面替换 + 登记 |
| 8 | `playground.rewrite_prompt` | `LLMRunner.run_text` | 执行截面替换 + 登记 |

按弃用纪律（记忆 feedback-no-deprecation-wrapping）：旧的 `_ainvoke_llm`/`default_complete_fn`
等私有 helper **直接删**，不留 @deprecated、不留 fallback 双路径。

## 8. 落地批次

- **B0 骨架**：建包 + pyproject + workspace + importlinter + `base.py`/`registry.py`/`__init__`。
- **B1 样板（judge，#1）**：执行截面改走 `LLMRunner`，跑 pytest + e2e 评测验证 trace/计费不变。← gate
- **B2 检索域（#9/#10/#11）**：classify/rewrite 通用任务整体迁，engine 改调。
- **B3 评测域剩余（#2/#3/#4/#5）**：dsl/ai_generate/optimizer 执行截面替换。
- **B4 工作流+会话（#6/#7/#8）**：generator/suggest/rewrite_prompt。
- **B5 收尾**：registry 全登记核对、删尽旧 helper、import-linter 绿、全量 pytest、CHANGELOG。

## 9. 验证策略

- 每批 `uv run pytest`（相关子包）+ `uv run lint-imports`（分层契约必须 GREEN）。
- B1 与 B3/B4 涉及评测：按记忆 eval-demo-data-seeding，用在线 7009 API 跑真实评测，
  浏览器核对 Trace 里 eval channel 的 generation 行 model/token/cost 仍正常落库（trace 不丢）。
- UI 无改动；若评测页展示受影响则按记忆 feedback-verify-ui-in-browser 截图核实。

## 10. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 改 trace scope 复用逻辑误覆盖 eval 归属，导致计费错位 | `run_text` 严格「已有 scope 不覆盖」；B1 样板专项验证 eval generation 行归属 |
| 业务特化输出契约适配回域内时丢字段 | 域内 parse 纯函数不动，仅替执行截面；diff 只在「怎么调」不在「怎么解析」 |
| import-linter 分层因 aikit 插入位置错误变红 | 先在 B0 跑 `lint-imports` 确认两契约 GREEN 再继续 |
| 评测全套件 pre-existing flakiness 干扰判断 | 按记忆 test-suite-state，只看本次相关用例增量，不追历史 71 失败 |

## 11b. 落地结果（2026-06-07 全量完成）

实操中归类有一处务实修正：**最终 12 处内部 LLM 用法全部留域内、仅收执行截面**——
原 §4 设想的「通用项 prompt/parse 整体迁入 aikit/tasks」未发生，因为现有内部用法
（分类 / 改写 / HyDE / 追问）都带域语义（检索改写、graph 节点、评测）。`tasks/` 目录与
`LLMTask` 基类**保留备未来真正跨域的通用能力**（如通用摘要 / 翻译），当前为空。

- 注入式纯算子（retrieval `expander` / dsl `evaluator`）统一改为 `complete_fn` 注入式，
  保可测设计，由注入点（`pipeline.default_complete_fn` / `runner._run_dsl_judge`）接 `LLMRunner`。
- 评测域各处自建的 `set_trace_context + try/finally + get_llm + ainvoke` 样板全删，
  改 `LLMRunner.run_text/run_stream(channel='eval', app_id, session_id)`；trace 归属不变。
- 排除项：graph `LLMNode`、`playground` 主流式调试 chat、`models.stream_test` 探活。

验证：import-linter 2 契约 GREEN；aikit 6 单测过；engine 检索 24 + graph 110 过
（`test_tool_node_with_registered_tool` 1 失败为 pre-existing，与本次无关）；system 378
测试零收集错误；ruff clean；净 −44 行（收口消重）。注册表 `list_tasks()` 列全 12 处。

**真实 e2e 已核验（2026-06-07）**：技术常识问答数据集（11 items）跑 judge=llm_judge +
model=qwen-plus，run 57014256469540864 success 11/11、mean_score=0.568。call_logs 窗口内
**22 条 channel='eval' generation 行**（=11×（被测调用+judge）），**22/22 全带
model_code/token/cost**（共 19170 token / $0.0264）→ trace 复用红线端到端生效，runner 外层
eval scope 被 LLMRunner 复用未覆盖，归属/计费零丢失。
注：首跑因运行中 uvicorn 进程是 uv sync 前启动的、命名空间包未拾取新 aikit（ModuleNotFoundError），
**完整重启进程后修复**——新增 workspace 包后必须重启 uvicorn，--reload 不够。

## 11. 收益

- 11 处重复执行代码收敛为 1 个执行器；新增内部 LLM 用法 = 写 1 个 task 或调 1 个 runner。
- `registry.py` 一览系统所有内部 LLM 用法（审计 / 成本归因 / 模型治理的单一入口）。
- 无 scope 的散调用（classifier/retrieval/generator）补上 `channel="internal"` 记账，可观测无死角。
- 评测域语义保持内聚（judges/dsl prompt 不外迁），分层单向干净。
