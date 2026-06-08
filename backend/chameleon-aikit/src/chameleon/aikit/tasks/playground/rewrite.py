"""System Prompt 即时改写（playground H1）。

当前 prompt + 一条不理想回答 + 用户改写诉求 → 改写后的新 System Prompt（单次 LLM）。
trace 归属（channel/app_id/session_id）由调用方按业务上下文注入（如评测域 channel='eval'）。
"""

from __future__ import annotations

from chameleon.aikit.base import LLMRunner


def _build_prompt(current_prompt: str, answer: str, instruction: str) -> str:
    """组装改写提示词（强约束只回纯文本，不带解释 / 代码块 / JSON 包裹）。"""
    base = current_prompt.strip() or "（当前没有 System Prompt）"
    return (
        "你是提示词工程助手。下面给你三样东西：\n"
        "1) 当前的 System Prompt\n"
        "2) 在该 System Prompt 下，模型对某次提问产出的一条不理想回答\n"
        "3) 用户对回答的改写诉求\n\n"
        "请基于这三者，改写出一个更好的 System Prompt，使模型按用户诉求作答。\n"
        f"=== 当前 System Prompt ===\n{base}\n\n"
        f"=== 这条不理想的模型回答 ===\n{answer.strip()}\n\n"
        f"=== 用户的改写诉求 ===\n{instruction.strip()}\n\n"
        "只输出改写后的完整 System Prompt 纯文本，"
        "不要任何解释、前后缀、Markdown 代码块或 JSON 包裹。"
    )


async def rewrite_prompt(
    current_prompt: str,
    answer: str,
    instruction: str,
    *,
    model: str | None = None,
    channel: str = "internal",
    app_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """基于一条不理想回答 + 改写诉求改写 System Prompt（单次 LLM，返回纯文本）。

    Args:
        current_prompt: 当前 System Prompt（可空）
        answer: 触发改写的那条不理想模型回答
        instruction: 用户的改写诉求（非空）
        model: 改写用模型 code；None 走系统默认
        channel / app_id / session_id: trace 归属，调用方按业务上下文传

    Returns:
        改写后的完整 System Prompt 纯文本（已 strip）

    Raises:
        BusinessError: 模型返回空内容
    """
    from chameleon.core.api.exceptions import BusinessError, ResultCode

    raw = await LLMRunner.run_text(
        _build_prompt(current_prompt, answer, instruction),
        model=model,
        channel=channel,
        app_id=app_id,
        session_id=session_id,
        retries=0,
    )
    rewritten = str(raw).strip()
    if not rewritten:
        raise BusinessError(ResultCode.Fail, message="改写失败，请调整需求后重试")
    return rewritten
