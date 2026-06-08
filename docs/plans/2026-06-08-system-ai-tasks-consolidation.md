# 系统 AI 任务统一收口 aikit（+ prompt 集中管理）

> 2026-06-08 · 分支 feat/agentkit-capabilities

## Context

系统内部用 LLM 的「AI 任务」（区别于用户创建的对外应用）共 **14 处，散在 6 个域、跨 3 个包**，prompt 大量行内拼接在业务代码里，难统一管理、难单独改 prompt。

`chameleon-aikit`（对内 AI 任务库）已经建好，但只收口了**执行**（`LLMRunner`）+ **索引**（`catalog` 注册表），**prompt 和任务逻辑还留在各域**（catalog 的 `location` 字段为证，只有 `media.intent_route` 真正搬进了 aikit）。

本计划完成「另一半」：把散落的 AI 任务 + prompt 统一迁进 `aikit/tasks/`，prompt 用集中 Python 常量模板（参考 sage `llm_deps.py` 范式 + 本仓 `media_intent.py` 标杆）。

## 现状清单（14 处）

| 域 | 用法 | 当前位置 | 迁移模式 |
|----|------|---------|---------|
| eval | judge / dsl规则 / 扩样 / 优化候选 / Prompt优化 / 对比分析 / 被测直调 | `system/datasets/*` | 多为带域依赖 |
| graph | 意图分类 / NL→图编排 / 追问建议 | `engine/graph/nodes/classifier.py`·`system/graphs/generator.py` | 纯数据 + 注入式 |
| retrieval | multi-query / HyDE | `engine/retrieval/expander.py` | 纯数据(已 complete_fn 注入) |
| playground | System Prompt 改写 | `system/playground/service.py` | 纯数据 |
| media | 生图意图路由 | `aikit/tasks/media_intent.py` | ✅ 已在 aikit |

## 目标架构

```
chameleon-aikit/src/chameleon/aikit/
├── base.py              # LLMRunner / LLMTask（已有）
├── catalog.py           # 注册表：location 指向 aikit/tasks（升级）
├── _json.py 🆕          # 通用 LLM 输出 JSON 抠取（extract_json，多处复用）
└── tasks/
    ├── media_intent.py  # 已有（标杆）
    └── graph/ 🆕        # 本次试点
        ├── __init__.py
        ├── classifier.py     # 纯数据：classify(query, categories, model)
        ├── followups.py      # 纯数据：suggest_followups(question, answer, model)
        └── graph_spec.py     # 注入式：generate_graph_spec(description, validate)
```

### 两种迁移模式（关键）

**分层铁律**：aikit 是底层包（被 engine/system 依赖），**不能反向依赖** engine/system。

1. **纯数据 task**（无域依赖）：输入原始数据（str/list/dict）、输出结构化结果。prompt 常量 + build + parse + fallback 全进 aikit。调用方瘦成一行。
   ```python
   # aikit/tasks/graph/classifier.py
   _SYSTEM = "你是意图分类器，只输出一个类别 key…"
   _PROMPT = "把用户问题分到下列类别之一…\n{categories}\n\n问题：{query}"
   async def classify(query: str, categories: list[dict], *, model=None) -> str: ...
   ```

2. **带域依赖 task**（校验/编排依赖 engine/system）：prompt + LLM 调用 + 重试搬 aikit，**域特定逻辑由调用方注入回调**。
   ```python
   # aikit/tasks/graph/graph_spec.py —— prompt 在此，图校验注入
   async def generate_graph_spec(description, *, validate: Callable[[dict], None], model=None) -> dict: ...
   # system/graphs/generator.py —— 注入 engine.graph 校验
   await generate_graph_spec(desc, validate=lambda s: Orchestrator(GraphSpec.model_validate(s)))
   ```

## 试点：graph 域（3 处）

1. `aikit/tasks/graph/classifier.py`：从 `ClassifierNode.execute` 抽出 prompt → `classify()`；engine 节点改调它。
2. `aikit/tasks/graph/followups.py`：从 `generator.suggest_followups` 抽 prompt → `suggest_followups()`；system 改调它（保留对外签名）。
3. `aikit/tasks/graph/graph_spec.py`：搬 `_SYSTEM_PROMPT` + 双轮重试 + trace scope；`validate` 注入；system `generate_graph_spec` 变薄壳注入 engine 校验。
4. `aikit/_json.py`：抽 `_extract_json`（generator + media_intent + 未来 eval judge 共用）。
5. `catalog.py`：3 条 location 改指 `aikit.tasks.graph.*`。

## 后续路线（试点验证后照搬）

- retrieval（2 处，纯数据，已 complete_fn 注入，最易）→ playground（1 处，纯数据）→ graph 剩余 → **eval（7 处，最大，多带域依赖，最后做）**。
- 每个域：纯数据整体搬 / 带域依赖注入式；catalog location 跟着更新；逐域回归。

## 验证

- 单测：`classify` 三类分流、`suggest_followups` 解析 3 条、`generate_graph_spec` 注入 validate 双轮重试。
- 跑通：graph 编辑器「AI 生成工作流」（generate_spec）、classifier 节点分流、追问建议——后端进程内真实 LLM。
- 分层守护：`import-linter` 契约确认 aikit 未新增对 engine/system 的依赖。
