"""chameleon-aikit —— 对内 AI 任务库。

系统内部「用 LLM 丰富功能」的统一栖身处：执行层（LLMRunner / LLMTask）+ 通用任务
（tasks/）+ 注册表（registry）。与对外智能体运行时 chameleon-agentkit 严格区分——
aikit 面向系统自身一次性、结构化的内部调用，agentkit 面向对外会话式智能体。

详见 docs/plans/2026-06-07-internal-llm-aikit.md。
"""

# import 即触发业务特化项的集中登记（通用任务在各自 tasks/*.py 自登记）
from chameleon.aikit import catalog as _catalog  # noqa: E402,F401
from chameleon.aikit.base import (
    DEFAULT_CHANNEL,
    LLMRunner,
    LLMTask,
    Prompt,
)
from chameleon.aikit.registry import (
    INTERNAL_LLM_TASKS,
    TaskSpec,
    list_tasks,
    register,
)

__all__ = [
    "DEFAULT_CHANNEL",
    "INTERNAL_LLM_TASKS",
    "LLMRunner",
    "LLMTask",
    "Prompt",
    "TaskSpec",
    "list_tasks",
    "register",
]
