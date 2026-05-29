"""ragas_context_precision —— 检索精度

算法：
  对 contexts 中每个 chunk 调 judge_fn 问 "这个 chunk 对回答 question 是否有用？yes/no"
  score = #有用的 chunk / #总 chunk
"""

from __future__ import annotations

import asyncio

from chameleon.engine.eval.algorithms import register_algorithm
from chameleon.engine.eval.algorithms.judge_helpers import (
    default_judge_fn,
    parse_yes_no,
)


async def ragas_context_precision(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
    config: dict | None = None,
    judge_fn=None,
) -> float:
    _ = answer, ground_truth, config
    if not contexts:
        return 0.0
    judge = judge_fn or default_judge_fn

    prompts = [
        (
            "请判断下面的「参考资料片段」是否对回答给定问题有用。"
            "只回答 yes 或 no。\n\n"
            f"问题：{question}\n\n"
            f"参考资料片段：{c}"
        )
        for c in contexts
    ]
    answers = await asyncio.gather(*[judge(p) for p in prompts])
    useful = sum(1 for a in answers if parse_yes_no(a))
    return useful / len(contexts)


register_algorithm("ragas_context_precision", ragas_context_precision)
