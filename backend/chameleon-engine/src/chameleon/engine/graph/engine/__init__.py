"""并发 GraphEngine（v1.1 替换串行 executor.py）

子模块：
- state.py        GraphExecState + VariablePool（运行时数据 / 状态容器）
- ready_queue.py  入度归零的节点入队（asyncio.Queue 封装 + 拓扑维护）
- worker_pool.py  asyncio.Semaphore 控制并发 + create_task 调度 [PR89]
- orchestrator.py 主循环：拉队列 → 调 worker → 收事件 → 更新状态 [PR89]

设计原则：
- Node API 完全兼容（红线：现 Node.execute() 签名不许动）
- 不依赖 DB / Redis；纯内存数据结构（DB 写入由 GraphRunner service 层负责）
- 事件流走现 SSE 协议（chameleon.data.infra.sse.SSEEventKind）

借鉴：/Users/links/Coding/Hub/dify/api/core/workflow/graph_engine/ 模块化思路
（不直接 cp 代码；Go-flavor → asyncio + dataclass + Pydantic 重写）
"""

from chameleon.engine.graph.engine.event_manager import (
    GraphEventManager,
    GraphNodeEventPayload,
)
from chameleon.engine.graph.engine.orchestrator import Orchestrator, OrchestratorConfig
from chameleon.engine.graph.engine.ready_queue import ReadyQueue
from chameleon.engine.graph.engine.state import GraphExecState, VariablePool
from chameleon.engine.graph.engine.worker_pool import WorkerPool

__all__ = [
    "GraphEventManager",
    "GraphExecState",
    "GraphNodeEventPayload",
    "Orchestrator",
    "OrchestratorConfig",
    "ReadyQueue",
    "VariablePool",
    "WorkerPool",
]
