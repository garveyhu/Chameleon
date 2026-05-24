"""GraphEngine —— 可视化工作流引擎

公开符号：
- `NodeSpec` / `EdgeSpec` / `GraphSpec`：图结构的 Pydantic 声明
- `Node[NodeDataT]` / `NodeStatus`：节点抽象基类 + 状态枚举
- `NodeContext`：节点执行时的只读运行时上下文
- `NodeRunResult` / `RunResult`：执行结果 DTO

调度器在 `chameleon.core.graph.engine`（并发 Orchestrator + WorkerPool +
ReadyQueue + GraphExecState）。

业务侧 import 路径：
    from chameleon.core.graph import GraphSpec, NodeContext
    from chameleon.core.graph.engine import Orchestrator
"""

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node, NodeStatus
from chameleon.core.graph.results import NodeRunResult, RunResult
from chameleon.core.graph.types import (
    EdgeSpec,
    GraphSpec,
    NodeSpec,
)

# 触发内置节点（noop / start / end）注册 + 业务节点（kb / llm / tool / if_else / agent_debate）注册
from chameleon.core.graph import registry  # noqa: F401
from chameleon.core.graph import nodes  # noqa: F401

__all__ = [
    "EdgeSpec",
    "GraphSpec",
    "Node",
    "NodeContext",
    "NodeRunResult",
    "NodeSpec",
    "NodeStatus",
    "RunResult",
]
