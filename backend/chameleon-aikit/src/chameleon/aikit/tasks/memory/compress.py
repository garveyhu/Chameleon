"""observational memory · 压缩编排 —— Observer → Reflector 串联（系统 AI 任务）。

把"既有整合观察 + 一段新对话"压成"更新后的整合观察"：先 Observer 抽新观察，再 Reflector
合并进既有。纯 AI 编排（无持久化——落库/触发由调用方按其 scope 负责），LLM 经 complete_fn
注入便于单测。
"""

from __future__ import annotations

from chameleon.aikit.tasks.memory.observer import CompleteFn, observe
from chameleon.aikit.tasks.memory.reflector import reflect


async def compress_observations(
    existing: str,
    conversation: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> str:
    """从新对话抽观察并合并进既有整合观察，返更新后的整合观察。

    Args:
        existing: 既有整合观察（可空）。
        conversation: 本次要压缩的对话记录文本。
        complete_fn: 注入的 LLM 补全 callable；None 用默认（两步共用）。

    Returns:
        更新后的整合观察文本；无新观察时原样返 existing。
    """
    new = await observe(conversation, complete_fn=complete_fn)
    if not new:
        return (existing or "").strip()
    return await reflect(existing, new, complete_fn=complete_fn)
