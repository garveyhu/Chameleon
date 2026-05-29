"""GraphEngine —— 可视化工作流引擎

公开符号：
- `NodeSpec` / `EdgeSpec` / `GraphSpec`：图结构的 Pydantic 声明
- `Node[NodeDataT]` / `NodeStatus`：节点抽象基类 + 状态枚举
- `NodeContext`：节点执行时的只读运行时上下文
- `NodeRunResult` / `RunResult`：执行结果 DTO

调度器在 `chameleon.engine.graph.engine`（并发 Orchestrator + WorkerPool +
ReadyQueue + GraphExecState）。

业务侧 import 路径：
    from chameleon.engine.graph import GraphSpec, NodeContext
    from chameleon.engine.graph.engine import Orchestrator
"""

# 触发内置节点（noop / start / end）注册 + 业务节点（kb / llm / tool / if_else / agent_debate）注册
from chameleon.engine.graph import (
    nodes,  # noqa: F401
    registry,  # noqa: F401
)
from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node, NodeStatus
from chameleon.engine.graph.results import NodeRunResult, RunResult
from chameleon.engine.graph.types import (
    EdgeSpec,
    GraphSpec,
    NodeSpec,
)

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
