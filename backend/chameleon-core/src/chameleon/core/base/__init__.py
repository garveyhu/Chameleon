"""Chameleon agent 抽象基类（吸收 sage core/base 习惯）

所有本地 agent 都是 BaseAgent 子类，由 LocalProvider 识别调用。

类型：
- BaseAgent: ABC，含 get_metadata() / astream() classmethod
- AgentMetadata: dataclass，agent 的"身份卡"
- AgentConfigOption: dataclass，前端可渲染的配置项
- AgentContext: dataclass，运行时上下文（app_id / session_id / 业务 vars）
- agent_router: 全局注册中心（仿 sage AgentRouter）
"""

from chameleon.core.base.agent_context import AgentContext
from chameleon.core.base.agent_router import AgentRouter, agent_router
from chameleon.core.base.base_agent import (
    AgentConfigOption,
    AgentMetadata,
    BaseAgent,
)

__all__ = [
    "AgentConfigOption",
    "AgentContext",
    "AgentMetadata",
    "AgentRouter",
    "BaseAgent",
    "agent_router",
]
