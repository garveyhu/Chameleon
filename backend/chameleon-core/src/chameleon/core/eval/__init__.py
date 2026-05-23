"""chameleon.core.eval —— 评判算子（RAGAS 内置 + 注册表）

红线（plan §2 P21）：
- ⛔ RAGAS builtin 算子不允许用户改 weight / metric definition；要 customize
  走 EvalTemplate.config 字段
- ⛔ judge LLM 调用必须可 mock —— 算子接 judge_fn callable，测试时注入 fake

算子签名（统一 ABC）：
    async def score(
        *,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None,
        config: dict | None,
        judge_fn: JudgeFn | None,
    ) -> float    # [0.0, 1.0]
"""

from chameleon.core.eval.algorithms import (
    REGISTRY,
    AlgorithmFn,
    JudgeFn,
    get_algorithm,
    list_algorithms,
)

__all__ = [
    "REGISTRY",
    "AlgorithmFn",
    "JudgeFn",
    "get_algorithm",
    "list_algorithms",
]
