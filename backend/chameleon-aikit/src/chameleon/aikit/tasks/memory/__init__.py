"""memory 域系统 AI 任务（observational memory：Observer 抽观察 / Reflector 合并）。

纯算子 + complete_fn 注入；``default_memory_complete_fn`` 经 LLMRunner 执行（memory channel）。
落库 / 触发 / 注入由 agentkit runner（providers-local）按其 scope 编排，AI 内核在此。
"""

from chameleon.aikit.tasks.memory.compress import compress_observations
from chameleon.aikit.tasks.memory.observer import (
    MEMORY_CHANNEL,
    CompleteFn,
    default_memory_complete_fn,
    observe,
)
from chameleon.aikit.tasks.memory.reflector import reflect

__all__ = [
    "MEMORY_CHANNEL",
    "CompleteFn",
    "compress_observations",
    "default_memory_complete_fn",
    "observe",
    "reflect",
]
