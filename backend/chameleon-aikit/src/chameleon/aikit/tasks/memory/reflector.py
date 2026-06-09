"""observational memory · Reflector —— 合并新旧观察（系统 AI 任务，memory 域）。

纯算子：LLM 经 ``complete_fn`` 注入。把既有观察与本轮新观察合并去重、压缩冗余、消解
矛盾（新覆盖旧），输出整合后的稠密观察。非破坏式——调用方保留原始条目，本任务只产出
合并视图。

红线：LLM 失败 → 回退「旧观察 + 新观察」朴素拼接（绝不丢已有事实）。
"""

from __future__ import annotations

from loguru import logger

from chameleon.aikit.tasks.memory.observer import (
    CompleteFn,
    default_memory_complete_fn,
)

_REFLECT_PROMPT = """\
你是用户画像整合器。下面是关于同一用户的「已有观察」和「新观察」。请把两者合并成一份\
整合后的观察清单。

要求：
- 每行一条观察，不加序号 / 引号 / 解释
- 去重：语义重复的只保留一条（信息更全的那条）
- 消解矛盾：新观察与旧观察冲突时，以**新观察**为准
- 压缩：相关的细碎观察可合并成一条更稠密的
- 保留所有不冲突的关键事实，不要丢信息
- 用与观察相同的语言

已有观察：
{existing}

新观察：
{new}
"""


async def reflect(
    existing: str, new: str, *, complete_fn: CompleteFn | None = None
) -> str:
    """合并已有观察与新观察，输出整合后的稠密观察文本。

    Args:
        existing: 既有整合观察（可空）。
        new: 本轮新抽取的观察（可空）。
        complete_fn: 注入的 LLM 补全 callable；None 用默认。

    Returns:
        整合后的观察文本；一方为空时返另一方；LLM 失败时朴素拼接（不丢事实）。
    """
    existing = (existing or "").strip()
    new = (new or "").strip()
    if not existing:
        return new
    if not new:
        return existing
    fn = complete_fn or default_memory_complete_fn()
    try:
        raw = await fn(_REFLECT_PROMPT.format(existing=existing, new=new))
    except Exception:
        logger.exception("reflect memory failed | 回退新旧朴素拼接")
        return f"{existing}\n{new}"
    merged = (raw or "").strip()
    return merged or f"{existing}\n{new}"
