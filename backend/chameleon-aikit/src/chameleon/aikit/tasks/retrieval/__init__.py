"""retrieval 域系统 AI 任务（multi-query 改写 / HyDE 假设答案）。

纯算子 + complete_fn 注入；``default_complete_fn`` 经 LLMRunner 执行。pipeline 把这些
算子接到真实 pgvector + PG FTS 上（接线在 engine，AI 内核在此）。
"""

from chameleon.aikit.tasks.retrieval.expander import (
    DEFAULT_MULTI_QUERY_N,
    CompleteFn,
    default_complete_fn,
    expand_queries,
    hyde_query,
)

__all__ = [
    "CompleteFn",
    "DEFAULT_MULTI_QUERY_N",
    "default_complete_fn",
    "expand_queries",
    "hyde_query",
]
