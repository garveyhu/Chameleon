"""ragas_faithfulness —— answer 中每句是否被 context 支持

算法：
  1. answer 按 [。！？.!?] 切句
  2. 对每句调 judge_fn(prompt) 问 "context 是否支持这句话？yes/no"
  3. score = #支持的句 / #总句

config:
  { "judge_max_concurrency": 4 }  # 暂未用；保留扩展
"""

from __future__ import annotations

import asyncio
import re

from chameleon.core.eval.algorithms import register_algorithm
from chameleon.core.eval.algorithms.judge_helpers import (
    default_judge_fn,
    parse_yes_no,
)

_SENT_SPLIT = re.compile(r"[。！？.!?\n]+")


async def ragas_faithfulness(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
    config: dict | None = None,
    judge_fn=None,
) -> float:
    _ = question, ground_truth, config  # 未使用
    if not answer or not answer.strip():
        return 0.0
    if not contexts:
        return 0.0
    judge = judge_fn or default_judge_fn

    sentences = [s.strip() for s in _SENT_SPLIT.split(answer) if s.strip()]
    if not sentences:
        return 0.0

    context_text = "\n---\n".join(contexts)
    prompts = [
        (
            "请判断下面这个 chunk 中所引出的事实陈述，是否完全被"
            "「参考资料」支持。只回答 yes 或 no。\n\n"
            f"参考资料：\n{context_text}\n\n"
            f"陈述：{s}"
        )
        for s in sentences
    ]
    answers = await asyncio.gather(*[judge(p) for p in prompts])
    supported = sum(1 for a in answers if parse_yes_no(a))
    return supported / len(sentences)


register_algorithm("ragas_faithfulness", ragas_faithfulness)
