"""GraphEngine 内置 nodes 集合

import 本包即触发各 node 的 register_node_type 副作用。
"""

# 触发注册（顺序无关）
from chameleon.core.graph.nodes import if_else, kb, llm, tool  # noqa: F401

__all__ = ["if_else", "kb", "llm", "tool"]
