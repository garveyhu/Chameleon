"""chameleon.engine.agent —— A2A 协议 + AgentRunner

跨 agent 调用底座，给 graph 的 agent_debate 节点 / 业务自写编排提供统一入口。

红线（plan §2 P20）：
- ⛔ A2A 调用必须传 trace_id —— 串 observation tree，不可断链
- ⛔ budget_remaining 必须 > 0 —— 防互相调用 token 爆
- ⛔ depth < MAX_DEPTH (=3) —— 防递归爆栈
"""

from chameleon.engine.agent.a2a import (
    MAX_DEPTH,
    A2ACallSpec,
    A2AResult,
    AgentRunner,
    call_agent,
)

__all__ = [
    "MAX_DEPTH",
    "A2ACallSpec",
    "A2AResult",
    "AgentRunner",
    "call_agent",
]
