"""observational memory · Observer —— 从对话抽稠密观察（系统 AI 任务，memory 域）。

纯算子：LLM 经 ``complete_fn`` callable 注入（prompt → completion text），便于单测注 stub。
把长对话压成关于用户的稠密、持久观察（偏好 / 事实 / 目标），供 Reflector 合并 + 跨会话
注入，长对话上下文不爆窗口。

红线：LLM 失败 / 空入 → 返空串（绝不拖垮主调用——压缩是 best-effort 后台活）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger

from chameleon.aikit.base import LLMRunner

#: complete_fn 签名：prompt → completion text
CompleteFn = Callable[[str], Awaitable[str]]

#: observational memory 任务的 trace channel（trace 归属补记账）
MEMORY_CHANNEL = "memory"

_OBSERVE_PROMPT = """\
你是对话观察器。请从下面的「对话记录」中抽取关于**用户**的稠密、持久、值得长期记住的\
观察——偏好、身份/背景事实、目标、约束、反复出现的诉求。

要求：
- 每行一条观察，不加序号、不加引号、不加解释
- 只记**持久**信息（"用户偏好简洁回答"），丢弃一次性寒暄 / 临时上下文
- 用陈述句、第三人称指代用户（"用户……"）
- 没有值得记住的就输出空（不要编）
- 用与对话相同的语言

对话记录：
{conversation}
"""


def default_memory_complete_fn() -> CompleteFn:
    """生产用 LLM 文本补全适配器，经 aikit LLMRunner 执行 + trace（memory channel）。"""

    async def complete(prompt: str) -> str:
        return await LLMRunner.run_text(
            prompt, channel=MEMORY_CHANNEL, retries=0, fallback=""
        )

    return complete


async def observe(conversation: str, *, complete_fn: CompleteFn | None = None) -> str:
    """从对话抽取关于用户的稠密观察文本（每行一条）。

    Args:
        conversation: 拼好的对话记录文本。
        complete_fn: 注入的 LLM 补全 callable；None 时用 ``default_memory_complete_fn()``。

    Returns:
        观察文本（多行）；无内容 / LLM 失败时返空串。
    """
    if not conversation or not conversation.strip():
        return ""
    fn = complete_fn or default_memory_complete_fn()
    try:
        raw = await fn(_OBSERVE_PROMPT.format(conversation=conversation))
    except Exception:
        logger.exception("observe memory failed | 跳过本次观察")
        return ""
    return (raw or "").strip()
