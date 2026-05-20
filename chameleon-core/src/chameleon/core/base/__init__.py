"""Chameleon agent 抽象基类（吸收 sage core/base 习惯）

可选用法：本地 LangGraph agent 可以继承 BaseAgent 拿到统一脚手架；
也可以走 v1 最简模式（直接 export build_graph + AGENT_META 字典），
两种范式 LangGraphProvider 都识别。

类型：
- BaseAgent: ABC，含 get_metadata() classmethod + build_graph() abstract
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
