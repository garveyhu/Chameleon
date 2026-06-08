"""eval 域系统 AI 任务（裁判评分 / AI 扩样 / Prompt 优化 …）。

judge 契约 + prompt 构造 + 解析为纯函数（绝不 import LLM/integrations，守分层）；
真正的 LLM 调用在评测域 runner/service（编排层）经 LLMRunner 执行。
"""

from chameleon.aikit.tasks.eval.judges import (
    JUDGES,
    LLM_JUDGES,
    JudgeResult,
    ScoreScale,
    build_gsb_prompt,
    build_llm_score_prompt,
    contains,
    exact_match,
    list_judges,
    llm_judge,
    parse_gsb_result,
    parse_score_result,
)

__all__ = [
    "JUDGES",
    "LLM_JUDGES",
    "JudgeResult",
    "ScoreScale",
    "build_gsb_prompt",
    "build_llm_score_prompt",
    "contains",
    "exact_match",
    "list_judges",
    "llm_judge",
    "parse_gsb_result",
    "parse_score_result",
]
