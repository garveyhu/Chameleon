"""追问建议 —— 基于刚才的问答给 3 个可能的接续问题。纯数据接口。"""

from __future__ import annotations

from chameleon.aikit.base import LLMRunner

_SYSTEM = (
    "基于刚才的问答，给出 3 个用户可能想接着问的简短问题，"
    "每行一个，不要编号 / 不要多余文字。"
)
_PROMPT = "问题：{question}\n回答：{answer}\n\n3 个追问："


async def suggest_followups(
    question: str,
    answer: str,
    *,
    model: str | None = None,
) -> list[str]:
    """给 3 个建议追问（每行一个）。

    Args:
        question: 用户刚问的问题
        answer: 系统刚给的回答
        model: 生成用 LLM code（如嵌入式应用关联智能体的 default_model）；None 走默认

    Returns:
        最多 3 条追问；LLM 失败时返回空列表（容错不抛）
    """
    text = await LLMRunner.run_text(
        _PROMPT.format(question=question, answer=answer),
        model=model,
        system=_SYSTEM,
        retries=0,
        fallback="",  # 失败返空串 → 解析得空列表
    )
    lines = [
        ln.strip("-•0123456789. 　\t").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]
    return [ln for ln in lines if ln][:3]
