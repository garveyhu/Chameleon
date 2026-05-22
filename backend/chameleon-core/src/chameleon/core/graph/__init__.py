"""GraphEngine —— Dify 风可视化工作流引擎（P18.1）

公开符号：
- `NodeSpec` / `EdgeSpec` / `GraphSpec`：图结构的 Pydantic 声明
- `Node[NodeDataT]`：节点抽象基类（泛型 input/output 类型）
- `NodeContext`：节点执行时的只读运行时上下文
- `GraphExecutor`：DAG 拓扑驱动的执行器
- `RunResult` / `NodeRunResult`：执行结果

业务侧 import 路径：`from chameleon.core.graph import ...`
"""

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.executor import (
    GraphExecutor,
    NodeRunResult,
    RunResult,
)
from chameleon.core.graph.node_base import Node, NodeStatus
from chameleon.core.graph.types import (
    EdgeSpec,
    GraphSpec,
    NodeSpec,
)

__all__ = [
    "EdgeSpec",
    "GraphExecutor",
    "GraphSpec",
    "Node",
    "NodeContext",
    "NodeRunResult",
    "NodeSpec",
    "NodeStatus",
    "RunResult",
]
