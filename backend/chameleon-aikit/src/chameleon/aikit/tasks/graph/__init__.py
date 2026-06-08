"""graph 域系统 AI 任务（意图分类 / 追问建议 / NL→图编排）。

prompt 集中在各 task 模块（常量模板），逻辑经 LLMRunner 执行。带域依赖的
``generate_graph_spec`` 用注入式（图校验回调由调用方提供，保 aikit 不反依赖 engine）。
"""

from chameleon.aikit.tasks.graph.classifier import classify
from chameleon.aikit.tasks.graph.followups import suggest_followups
from chameleon.aikit.tasks.graph.graph_spec import GraphSpecError, generate_graph_spec

__all__ = ["classify", "suggest_followups", "generate_graph_spec", "GraphSpecError"]
