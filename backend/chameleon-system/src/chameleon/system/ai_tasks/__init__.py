"""ai_tasks 域 —— 系统内各种 AI 任务的统一异步执行 + 状态跟踪 + 结果缓存。

配合 chameleon-aikit（执行层）：aikit 跑 LLM，ai_tasks 负责异步调度 / 持久化 / 缓存去重。
各业务域通过 registry.register_handler 注册自己的 task_type handler。
"""

from chameleon.system.ai_tasks.api import router as ai_tasks_router
from chameleon.system.ai_tasks.registry import has_handler, register_handler

__all__ = ["ai_tasks_router", "has_handler", "register_handler"]
