# 本地智能体 SDK（agentkit）—— 深度优化本地开发体验

> 状态：设计稿，待 review
> 目标读者：框架维护者 + 未来用 SDK 接入的外部开发者

## 1. 背景与目标

平台有四种 agent 来源：`local`（用户写的 Python 子类）、`graph`（可视化编排）、`dify/fastgpt/coze`（外部平台）。
`graph` 已经把"模型 / 知识库 / 编排 / 可观测"在画布里闭环；但 **`local` 来源的开发体验停留在早期**：

- 调模型要自己 `import llm()`，且拿的是**全局默认**，页面配的模型对 local **根本不生效**。
- 调知识库 `cls.retrieve(ctx, q)` 已经联动页面配的 KB，但写法是 classmethod + 手动传 ctx，且**检索不自动记 citation**。
- trace 半自动：bridge（LangGraph/LCEL）会抽 usage，native 路径全靠手动 yield。
- 没有可冻结的公共面，谈不上给外部开发者用。

**目标**：让本地智能体开发"只写业务逻辑"——

> 需要调模型就用约定方法、页面配哪个用哪个（没配=默认）；需要检索就用约定方法、页面给 agent 配的 KB 自动联动；模型/KB 随时在 web 切换；调用日志/trace 全在 web 可见。这套调用包装**专门管理成一个版本化 SDK**，开发者用它本地开发自测，提交源码进 `chameleon-agents/` 即可注册运行；未来外部开发者也用同一套 SDK。

## 2. 现状盘点

| 关注点 | 现状 | file |
|---|---|---|
| 作者基类 | `BaseAgent`，classmethod 风格（`get_metadata` + `astream`/`build_graph`/`build_runnable`） | `chameleon-core/.../core/base/base_agent.py` |
| 运行上下文 | `InvokeContext`（input/history/session_id/app_id/request_id/context_vars…） | `chameleon-providers/base/.../base/types.py` |
| 模型获取 | `llm()` / `llm_by_name()`，**全局默认**，不看 agent 配置 | `core/components/inventory.py` + `llms/factory.py` |
| 模型路由 | `core.routing` 轮转 + failover，但仅 service 层对接，local 未用 | `chameleon-api/.../agent/service.py`（`invoke_with_failover`） |
| KB 检索 | `cls.retrieve(ctx, q)` 按 `agent_kb_link` 联动；不自动 citation | `base_agent.py` + `components/knowledge.py` |
| 可观测 | `observe()` contextmanager + contextvar；native 手动 | `core/observe/context.py` |
| 注册发现 | 启动扫描 `chameleon.agents.*` 命名空间 + 读 DB `agents` 行 | `chameleon-providers/base/.../registry.py` |
| 调用入口 | `LocalProvider.stream(ctx)` 动态 import → `agent_cls.astream(ctx)` | `chameleon-providers/local/.../provider.py` |
| 公共面 | `core.base.__all__` / `core.components.__all__`，无版本化 SDK | 同上 |
| 示例 | `qwen_chat`、`examples/echo_{native,langgraph,runnable}` | `backend/chameleon-agents/*` |

**结论**：KB 联动其实已经七成；模型绑定是真缺；trace 需补自动化；公共面要收拢冻结。

## 3. 北极星与作者体验

> **作者只写业务逻辑；模型、知识库、追踪都从一个绑定了「本 agent 页面配置 + 本次请求」的运行时 `ctx` 隐式拿到。** 作者永不 import `llm()`/`search_kb()`、不传 agent_key、不手写 trace。

```python
from chameleon.agentkit import agent, AgentRun, ModelSlot, Opt   # 唯一公共依赖

@agent(
    key="kefu-faq", name="客服 FAQ",
    models=[ModelSlot("chat", "主对话模型"),
            ModelSlot("fast", "改写/分类小模型", optional=True)],
    kb=True,                                       # 声明用 KB → 页面出现"关联 KB"
    config=[Opt("tone", "语气", choices=["专业", "活泼"], default="专业")],
)
async def handle(ctx: AgentRun):
    rewrite = await ctx.complete(slot="fast", user=ctx.query)         # 取页面配的 fast 槽模型
    docs = await ctx.kb.search(rewrite, top_k=3)                      # 页面配的 KB + 自动 citation
    async for delta in ctx.stream(                                    # 自动 generation span + usage
        slot="chat",
        system=f"你是客服，语气{ctx.config['tone']}",
        context=docs, user=ctx.query,
    ):
        yield delta
```

切模型、换 KB、调用日志去哪——全在 web 配/看，代码一行不动。

### 3.1 配置双源原则（web 便捷层 + 代码自由层）

> **web 配置是「降低简单 agent 门槛」的便捷层，不是必经之路。任何资源（模型 / KB / 自定义参数 / 工具）都必须能在代码里完全指定，绝对自由优先于便捷。**

**前提**：模型、KB 都来自平台**已配置的资源池**（「模型」页 / model.json → LLMFactory；KB 列表）。所有引用——无论 web 还是代码——都只能从这个池里挑，code/kb_key 都会**校验**，非法即报错。代码里**没有**"随便填一个模型 id 跑起来"这种事；引用模型 code 就是今天 `llm_by_name(code)` 的契约。

每种资源，"这个 agent 用哪个" 由谁决定，作者按需选（可混用）：

| 档 | 写法 | 谁决定用哪个（都来自已配置池） |
|---|---|---|
| **A. web 托管槽** | `@agent(models=[ModelSlot("chat")], kb=True)` + `ctx.llm("chat")` / `ctx.kb.search(q)` | web 在"关联模型/关联 KB"里从**已配置资源**选；代码可给默认兜底。运营随时切 |
| **B. 代码点名** | `ctx.llm(model="qwen-plus")`（model 必须命中已配置且启用的模型，否则报错）/ `ctx.kb.search(q, kbs=["faq"])`（kb_key 同理校验） | 代码直接指定用哪个已配置资源，**不必等 web 绑**——这就是"不依赖前端"的自由 |
| **C. 自带对象（逃生口，少用）** | `ctx.wrap(my_langchain_model)` | 绕过平台模型库 = 凭证/路由/计费都不经过；仅平台没有该模型的极端定制用，默认别走 |

- `ctx.llm()`（无参）= 系统默认模型，即今天的 `llm()`。
- `ctx.llm(model="...")` = 指定一个已配置模型，即今天的 `llm_by_name(...)`，只是包进 ctx 拿到自动 trace + routing。

**优先级（web 托管槽且代码也给了默认时）**：
- 默认 **web 绑定优先**（"运营随时切"的意义），代码 `default` 仅作 web 未绑定时的兜底。
- 作者要锁死就 `ModelSlot("chat", locked=True, default="qwen-plus")` → web 只读不可改，恒用代码默认；或直接走档 B 内联点名（本就不经过 web）。

结果：简单 agent 走档 A（几乎零代码 + 运营 web 可调）；复杂 agent 走档 B 在代码里直接点名已配置的模型/KB，**完全不依赖前端**；两者可在同一 agent 混用（对话模型走 web 托管、内部改写固定点名某小模型）。

## 4. 公共面（要冻结的 API）

`chameleon-agentkit` 包对外只暴露这些；其余（factory/routing/observe/kb/registry）一律私有：

```python
# 作者门面
agent(key, name, *, description=None, models=[], kb=False, config=[], tags=[]) -> decorator
class BaseAgent          # 高级/有状态用法（多节点、自定义 astream），底层共用 ctx

# 运行上下文（注入到 handle/astream）
class AgentRun:          # 即"绑定本 agent + 本请求"的 ctx
    query: str                      # 本轮用户输入（多模态时给规整文本）
    messages: list[Message]         # 含多模态块的完整输入
    history: list[Message]
    session_id: str | None
    config: dict                    # 页面配的自定义参数（按 Opt 声明）
    # —— 模型（slot=走绑定链；model=直接点名某已配置模型，=llm_by_name，二选一）——
    def llm(self, slot="chat", *, model=None) -> ChatModel         # 低层：配置好的 LangChain chat model
    async def complete(self, *, slot="chat", model=None, system=None, user, context=None, **kw) -> str
    def stream(self, *, slot="chat", model=None, ...) -> AsyncIterator[str]   # 高层糖，自动 trace+usage
    # —— 知识库 ——
    kb: KbHandle                    # ctx.kb.search(query, *, top_k=None, min_score=0.0) -> list[Doc]
    # —— 追踪 ——
    def span(self, name, type="span"): ...             # 可选手动分段；complete/kb 已自动开 span
    def emit(self, event): ...                         # 透传自定义 StreamEvent（高级）

# 声明类型
class ModelSlot(name, label, *, optional=False, default=None, locked=False)  # default/锁定都引用已配置模型 code
class Opt(key, label, *, type="string", choices=None, default=None, required=False)
@dataclass class Doc:  text; score; source; metadata
```

**冻结纪律**：公共面加字段只增不改；破坏性变更走 major 版本 + deprecation。内部实现随便重构。

## 5. 运行时 ctx 与可插拔 transport

`AgentRun` 的方法不直接碰 factory/kb，而是走一个 `RuntimeTransport` 接口；transport 两种实现：

```
AgentRun.complete/llm/kb.search/span
        │
        ▼
RuntimeTransport (抽象)
   ├── InProcessTransport   ← 提交进 chameleon-agents/ 后，服务端进程内跑
   │      llm  → core.routing + LLMFactory（按 agent 槽绑定解析）
   │      kb   → components.search_kb（按 agent_kb_link）
   │      span → core.observe
   └── HttpDevTransport     ← 本地自测：agentkit CLI 连 dev 服务
          llm  → POST {DEV_URL}/v1/dev/llm        （dev token 鉴权）
          kb   → POST {DEV_URL}/v1/dev/kb/search
          span → POST {DEV_URL}/v1/dev/trace
```

**同一份作者代码，两种跑法**：本地 `agentkit chat my_agent`（HttpDev，连 localhost:7009 自测）→ 自测通过 → 源码提交进 `chameleon-agents/` → 服务端 InProcess 运行。这既满足"提交进目录即注册运行"，又给出真实的本地自测闭环。

> dev 端点 `/v1/dev/*` 仅在开发态开放、需 dev token；生产可关。是否后续支持"远程托管 agent"（外部服务常驻、Chameleon 远程调）留作扩展——transport 抽象已为此预留。

## 6. 多具名模型槽

### 声明（代码）
`@agent(models=[ModelSlot("chat", ...), ModelSlot("fast", ..., optional=True)])`，槽定义随注册进入 registry metadata。

### 存储（DB）
每 agent × 槽绑定一个 model。两种方案：

- **方案 A（推荐）**：JSON 列 `agents.model_bindings = {"chat": <model_id>, "fast": <model_id>}`。简单、与现有 `config` JSON 同套路、无需 join；解析时校验 model 仍存在。
- 方案 B：独立表 `agent_model_binding(agent_id, slot, model_id)`，FK 完整性 + 级联，但每次解析多一次 join（可缓存）。

> 取 A：本地 agent 数量有限、解析在注册期/请求期都可缓存，JSON 足够；保留 B 作为规模化后的演进。

### 解析（运行时）
所有路径解析出的 model code **都校验命中「已配置且启用」的模型**，否则报错（不存在"随便填的 id"）。

- **档 A 槽解析** `ctx.llm("chat")`：`model_bindings["chat"]`（web 选的已配置模型）→ `ModelSlot.default`（代码兜底，也是已配置 code）→ 系统默认。
- **档 B 点名** `ctx.llm(model="qwen-plus")`：直接解析指定的已配置模型（= 今天的 `llm_by_name`），不经过 web 绑定。
- `ctx.llm()` 无参 = 系统默认（= 今天的 `llm()`）。
- `ModelSlot("chat", locked=True, default="qwen-plus")`：web 只读不可改，恒用代码默认。

解析出 model 后**统一走 `core.routing`** 拿带轮转/failover 的实例；返回的低层对象就是 LangChain chat model，作者可任意 LCEL 组合。
档 C 逃生口 `ctx.wrap(model)` 仅在平台模型库确实没有该模型时用，绕过 routing/凭证管理，默认别走。

### UI
详情页"关联模型" tab（当前空占位）改为：读 registry 的槽声明 + DB 绑定，每槽一个模型下拉（Radix），留空=用默认。`graph` 来源不显示（已隐藏）。

## 7. KB 绑定 + 自动 citation

- **档 A（web 托管）**：`ctx.kb.search(q)` 走 `agent_kb_link`（页面"关联 KB"配的），返回 `list[Doc]`；`@agent(kb=True)` 才在详情页显示"关联 KB" tab。
- **档 B（代码钉死）**：`ctx.kb.search(q, kbs=["faq", "policy"])` 显式指定 kb_key，绕过 web 关联，完全代码控制。
- **档 C（自带）**：作者可不调 `ctx.kb`，自己持有 retriever / 向量库，照样能用 `ctx.span()` 把检索纳入 trace。
- **自动 citation**：A/B 路径 search 内部自动 `emit(StreamEvent(type=citation, ...))`，作者不用手动 yield；web 引用卡片自动出。
- 兼容：`BaseAgent.retrieve` 保留为底层，`ctx.kb.search` 是其门面 + 自动 trace。

## 8. 环境式 trace

`ctx.complete` / `ctx.stream` / `ctx.kb.search` 内部自动用 `observe()` 开 span（generation / retrieval），usage 自动归集、父子自动嵌套（沿用 contextvar）。native 作者**零样板**即得完整 trace 树。`ctx.span(...)` 给需要手动分段的高级场景。

## 9. 配置 Schema → 自动表单

- `@agent(config=[Opt(...)])` 声明运营可调参数；值存 `agents.config` JSON（已存在），运行时进 `ctx.config`。
- 同 §3.1 双源：`Opt` 有 `default`（代码 fallback），web 表单值优先；不声明 Opt 的参数作者照样能在代码里写死常量——web 只是可选调参层。
- 详情页"基础信息"下自动渲染表单（按 Opt 类型：string/number/bool/choices），保存写回 `config`。
- 复用既有 `AgentConfigOption`（目前没接 UI）的概念，统一到 `Opt`。

## 10. 分发与注册 + 本地自测

### 开发者工作流（目标）
1. `pip install chameleon-agentkit`，在自己项目里写 `@agent`/`handle`。
2. `agentkit chat my_agent`（或 `agentkit run`）连 dev 服务（HttpDevTransport）本地自测，验证模型/KB/trace 都通。
3. 把 agent 包源码提交进 `backend/chameleon-agents/<name>/`。
4. 服务端发现（entry-points 优先，命名空间扫描兜底）+ 自动建/更新 DB `agents` 行 → 注册运行。

### 注册机制
- 从纯命名空间扫描升级为 **entry-points**（`[project.entry-points."chameleon.agents"]`），外部包不在命名空间下也能注册;命名空间扫描保留兼容。
- 新增"同步 agent 注册"动作：扫描到代码声明但 DB 无行 → 自动 seed 一行（enabled 默认按策略）；声明的 models/config 槽写入 registry，绑定值由运营在 web 填。

## 11. 存量迁移

- `BaseAgent` 不删，降为底层；`get_metadata`/`astream`/`build_graph`/`build_runnable` 全保留。
- `qwen_chat`、`examples/echo_*` 逐个迁到 `@agent`/`ctx`（顺带当 SDK 用法范例）；保留至少一个 BaseAgent 写法的范例。
- `llm()` 全局默认作为"系统默认"语义保留，但 agent 内部改用 `ctx.llm(slot)`。

## 12. 分期计划

- **Phase 0 — 公共面冻结**：新建 `chameleon-agentkit` 包，定义 `agent`/`AgentRun`/`ModelSlot`/`Opt`/`Doc` 签名与 `RuntimeTransport` 抽象（先空壳 + 类型）。产出：可 import、tsc 级别稳定的 API 面。
- **Phase 1 — 进程内 ctx + 多槽模型**：`InProcessTransport`；`agents.model_bindings`（方案 A）+ 解析走 `core.routing`；`ctx.llm/complete/stream` 打通。详情页"关联模型" tab 接上多槽下拉。迁移 `qwen_chat` 验证。
- **Phase 2 — KB 门面 + 自动 citation + 环境 trace**：`ctx.kb.search`、`complete/kb` 自动 span/usage/citation。迁移 `echo_native` 验证 trace 树。
- **Phase 3 — 配置 Schema→表单**：`@agent(config=[Opt])` → 详情页自动表单 → `ctx.config`。
- **Phase 4 — entry-points 注册 + 注册同步**：发现机制升级 + "代码声明→DB 行"同步动作。迁移剩余 example。
- **Phase 5 — 本地自测 CLI + dev 端点**：`agentkit chat/run` + `HttpDevTransport` + `/v1/dev/{llm,kb,trace}`（dev token）。文档 + 一个"从零写 agent"的 quickstart。

每期：tsc/ruff + 单测 + 浏览器验证（详情页表单、运行日志/trace 树）。

## 13. 风险与开放问题

- **进程内信任边界**：提交进 `chameleon-agents/` 的代码跑在主进程里，等同信任源码（走 PR review）。沙箱化（子进程/容器）是否要、何时要？（Code 节点已有 sandbox runtime，可借鉴）
- **多槽 vs 简单**：先上 2~3 个常见槽（chat/fast/reasoning）是否够？槽是固定枚举还是 agent 自由命名？（当前设计：agent 自由声明）
- **dev 端点暴露面**：`/v1/dev/llm` 等会把模型调用暴露给本地开发，需 dev token + 仅 dev profile 开。
- **存量 InvokeContext 与 AgentRun 关系**：`AgentRun` 是 `InvokeContext` 的"作者友好门面"（包一层），还是替换？建议包一层，底层不动。
- **方案 A 的 model_id 失效**：JSON 里存的 model 被删/停用 → 解析降级到默认 + 在 web 标记"绑定已失效"。
