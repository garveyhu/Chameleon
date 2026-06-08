"""入站开放 A2A —— 把自家 agent 暴露成标准 Agent2Agent 端点（/a2a）。"""

from chameleon.api.a2a.api import router as a2a_router

__all__ = ["a2a_router"]
