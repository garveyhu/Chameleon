"""ragas_context_recall —— 检索召回

算法：
  对 ground_truth 切句；每句调 judge_fn 问 "contexts 是否包含支持这句话的内容？yes/no"
  score = #命中的 GT 句 / #GT 总句

依赖 ground_truth，必须传；否则返 0.0。
"""

from __future__ import annotations

import asyncio
import re

from chameleon.engine.eval.algorithms import register_algorithm
from chameleon.engine.eval.algorithms.judge_helpers import (
    default_judge_fn,
    parse_yes_no,
)

_SENT_SPLIT = re.compile(r"[。！？.!?\n]+")


async def ragas_context_recall(
    *,
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: str | None = None,
    config: dict | None = None,
    judge_fn=None,
) -> float:
    _ = question, answer, config
    if not ground_truth or not contexts:
        return 0.0
    judge = judge_fn or default_judge_fn

    gt_sents = [s.strip() for s in _SENT_SPLIT.split(ground_truth) if s.strip()]
    if not gt_sents:
        return 0.0
    context_text = "\n---\n".join(contexts)

    prompts = [
        (
            "请判断「参考资料」中是否包含足以支持下面这句话的内容。"
            "只回答 yes 或 no。\n\n"
            f"参考资料：\n{context_text}\n\n"
            f"句子：{s}"
        )
        for s in gt_sents
    ]
    answers = await asyncio.gather(*[judge(p) for p in prompts])
    covered = sum(1 for a in answers if parse_yes_no(a))
    return covered / len(gt_sents)


register_algorithm("ragas_context_recall", ragas_context_recall)
