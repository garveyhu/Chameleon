"""bridges/ —— 编排框架 → StreamEvent 翻译桥（实现层）

本地 agent 可以从这里 import helper，把 LangGraph CompiledGraph 或
LangChain Runnable 的输出自动翻成 Chameleon 的 StreamEvent。

设计目标：让"我用 LangGraph 写 agent"和"我用 LangChain LCEL 写 agent"
和"我用纯 Python 异步生成器写 agent"三种风格无缝接入，agent 作者只
负责"产 StreamEvent"——具体怎么产由他自由选择。

对外契约（输入 InvokeContext/Message、输出 StreamEvent）由 chameleon.providers.base.types
承载；这里是依赖 langchain_core 的具体翻译实现，已迁出 core。
"""

from chameleon.integrations.bridges.langchain_bridge import astream_from_runnable
from chameleon.integrations.bridges.langgraph_bridge import (
    astream_from_langgraph_graph,
    ctx_to_langgraph_messages,
)


def wire_agent_bridges() -> None:
    """把 langgraph / runnable 桥注入 core.base 的桥注册表。

    应用启动（chameleon-app create_app）与测试 conftest 调一次；之后 BaseAgent.astream
    在 agent 定义 build_graph()/build_runnable() 时即可经注册表委托到这里的实现，
    避免 core 反向 import integrations。
    """
    from chameleon.core.base.bridge_registry import (
        set_langgraph_bridge,
        set_runnable_bridge,
    )

    set_langgraph_bridge(astream_from_langgraph_graph)
    set_runnable_bridge(astream_from_runnable)


__all__ = [
    "astream_from_langgraph_graph",
    "astream_from_runnable",
    "ctx_to_langgraph_messages",
    "wire_agent_bridges",
]
