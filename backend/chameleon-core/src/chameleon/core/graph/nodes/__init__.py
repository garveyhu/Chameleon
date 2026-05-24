"""GraphEngine 内置 nodes 集合

import 本包即触发各 node 的 register_node_type 副作用。
"""

# 触发注册（顺序无关）
from chameleon.core.graph.nodes import (  # noqa: F401
    agent_debate,
    aggregator,
    answer,
    http,
    human_input,
    if_else,
    iteration,
    kb,
    llm,
    parallel,
    template,
    tool,
)

__all__ = [
    "agent_debate",
    "aggregator",
    "answer",
    "http",
    "human_input",
    "if_else",
    "iteration",
    "kb",
    "llm",
    "parallel",
    "template",
    "tool",
]
