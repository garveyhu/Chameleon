"""系统内部 LLM 用法的集中登记（全量索引）。

满足「一个地方看全系统在哪用了 LLM」诉求（计划 §4）。**所有**内部 LLM 调用点都
登记一条 `TaskSpec`——它们的 prompt/parse 留在各自域内（保域内聚 + 守分层），aikit
只收口其执行截面（经 LLMRunner / 注入式 complete_fn）。此处用**纯数据 TaskSpec** 声明
元信息，只含字符串路径，不 import 任何业务模块，故不产生分层反向依赖。import
`chameleon.aikit` 即触发登记，`list_tasks()` 一览全表。

排除项（非「系统用 LLM 丰富功能」，不登记）：
- graph LLMNode —— 用户在工作流里编排的 LLM 节点，是产品功能本身。
- playground 主流式 / model 连通性测试 —— 调试 chat 与运维探活。
"""

from __future__ import annotations

from chameleon.aikit.registry import TaskSpec, register

_SPECS: list[TaskSpec] = [
    # ── 评测域 ──────────────────────────────────────────────
    TaskSpec(
        key="eval.judge",
        title="LLM 评分（llm_judge / llm_score / gsb）",
        domain="eval",
        channel="eval",
        location="system.datasets.runner._run_llm_judge + judges.py（build/parse 纯函数）",
    ),
    TaskSpec(
        key="eval.dsl_nl_rules",
        title="DSL 自然语言规则评分",
        domain="eval",
        channel="eval",
        location="system.datasets.dsl.evaluator._score_nl_rules（complete_fn 注入式）",
    ),
    TaskSpec(
        key="eval.ai_generate",
        title="AI 扩样（种子 few-shot 流式生成候选）",
        domain="eval",
        channel="eval",
        location="system.datasets.ai_generate.ai_generate_stream",
    ),
    TaskSpec(
        key="eval.refine_candidate",
        title="评测候选单条优化 / 再生成",
        domain="eval",
        channel="eval",
        location="system.datasets.ai_generate.refine_candidate",
    ),
    TaskSpec(
        key="eval.optimize",
        title="运行级 Prompt 优化（低分样本→重写 Prompt）",
        domain="eval",
        channel="eval",
        location="system.datasets.optimizer._llm_optimize",
    ),
    TaskSpec(
        key="eval.compare_analysis",
        title="运行对比 AI 总结分析（多模型逐题对比→markdown 报告）",
        domain="eval",
        channel="internal",
        location="system.datasets.service.analyze_comparison",
    ),
    TaskSpec(
        key="eval.subject_invoke",
        title="评测被测模型直调（preview→answer）",
        domain="eval",
        channel="eval",
        location="system.datasets.runner._invoke_for_item",
    ),
    # ── 工作流 / 会话域 ──────────────────────────────────────
    TaskSpec(
        key="graph.classifier",
        title="意图分类节点",
        domain="graph",
        channel="internal",
        location="engine.graph.nodes.classifier.ClassifierNode.execute",
    ),
    TaskSpec(
        key="graph.generate_spec",
        title="NL→GraphSpec 工作流自动编排",
        domain="graph",
        channel="internal",
        location="system.graphs.generator.generate_graph_spec",
    ),
    TaskSpec(
        key="graph.suggest_followups",
        title="追问建议生成",
        domain="graph",
        channel="internal",
        location="system.graphs.generator.suggest_followups",
    ),
    # ── 知识库检索域 ────────────────────────────────────────
    TaskSpec(
        key="retrieval.multi_query",
        title="multi-query 检索改写",
        domain="retrieval",
        channel="internal",
        location="engine.retrieval.expander.expand_queries"
        "（pipeline.default_complete_fn 注入）",
    ),
    TaskSpec(
        key="retrieval.hyde",
        title="HyDE 假设性答案",
        domain="retrieval",
        channel="internal",
        location="engine.retrieval.expander.hyde_query"
        "（pipeline.default_complete_fn 注入）",
    ),
    # ── Playground 域 ──────────────────────────────────────
    TaskSpec(
        key="playground.rewrite_prompt",
        title="System Prompt 即时改写（H1）",
        domain="playground",
        channel="eval",
        location="system.playground.service.rewrite_prompt",
    ),
    # ── 媒体生成域 ──────────────────────────────────────────
    TaskSpec(
        key="media.intent_route",
        title="生图意图路由（文生图 / 图生图判别，langgraph）",
        domain="media",
        channel="internal",
        location="aikit.tasks.media_intent.route_media_intent"
        "（langgraph 图：detect 规则 + llm_judge 节点）",
        builtin_general=True,
    ),
]

for _spec in _SPECS:
    register(_spec)
