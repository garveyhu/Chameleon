"""GraphEngine 内置 nodes 集合

import 本包即触发各 node 的 register_node_type 副作用。
"""

# 触发注册
from chameleon.core.graph.nodes import kb, llm  # noqa: F401

__all__ = ["kb", "llm"]
