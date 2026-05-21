"""bridges/ —— 编排框架 → StreamEvent 翻译桥

本地 agent 可以从这里 import helper，把 LangGraph CompiledGraph 或
LangChain Runnable 的输出自动翻成 Chameleon 的 StreamEvent。

设计目标：让"我用 LangGraph 写 agent"和"我用 LangChain LCEL 写 agent"
和"我用纯 Python 异步生成器写 agent"三种风格无缝接入，agent 作者只
负责"产 StreamEvent"——具体怎么产由他自由选择。
"""

from chameleon.core.base.bridges.langchain_bridge import astream_from_runnable
from chameleon.core.base.bridges.langgraph_bridge import (
    astream_from_langgraph_graph,
    ctx_to_langgraph_messages,
)

__all__ = [
    "astream_from_langgraph_graph",
    "astream_from_runnable",
    "ctx_to_langgraph_messages",
]
