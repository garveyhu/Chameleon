"""GraphExecState + VariablePool —— 运行时状态容器

GraphExecState 是单次 graph run 的"账本"：每个节点的状态、累积输出、
错误、超时等。VariablePool 是节点输出的 key-value 池（按 node_id 索引），
供下游节点和 End 节点聚合。

红线：
- 所有写入必须通过本模块方法（不允许外部直接 mutate 字段）；保证并发安全。
- 数据结构内部用 asyncio.Lock 保护跨节点共享的字典写入。
- VariablePool 中的 value 必须 JSON-serializable（节点输出会落 graph_node_runs.output）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from chameleon.engine.graph.node_base import NodeStatus

# ── VariablePool ────────────────────────────────────────────────────


class VariablePool:
    """节点输出 / 全局变量容器（线程安全）

    用法：
        pool = VariablePool()
        await pool.set_output("node_a", {"answer": "hi"})
        out = await pool.get_output("node_a")
        snapshot = await pool.snapshot()   # End 节点聚合用

    并发模型：
        多个 worker 可能同时 set 不同 node_id 的 output；asyncio.Lock 保护字典。
        现有 5 节点串行图基本无并发竞争，但 Iteration / Parallel 节点会写并发。
    """

    def __init__(self) -> None:
        self._outputs: dict[str, Any] = {}
        # 全局变量（非节点输出，用于 graph input 透传 / system 注入）
        self._globals: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def set_output(self, node_id: str, output: Any) -> None:
        """记录节点输出；同一 node_id 后写覆盖前写（节点重跑场景）"""
        async with self._lock:
            self._outputs[node_id] = output

    async def get_output(self, node_id: str) -> Any:
        """读取节点输出；不存在时返回 None"""
        async with self._lock:
            return self._outputs.get(node_id)

    async def set_global(self, key: str, value: Any) -> None:
        async with self._lock:
            self._globals[key] = value

    async def get_global(self, key: str) -> Any:
        async with self._lock:
            return self._globals.get(key)

    async def snapshot(self) -> dict[str, Any]:
        """全量快照（节点输出 + 全局变量）；End 节点聚合用"""
        async with self._lock:
            return {
                "outputs": dict(self._outputs),
                "globals": dict(self._globals),
            }


# ── GraphExecState ──────────────────────────────────────────────────


@dataclass
class GraphExecState:
    """单次 graph run 的运行时账本

    被 Orchestrator 持有 + 各 worker 共享读写。所有跨 worker 共享字段都
    放在带 asyncio.Lock 保护的方法后面（不直接暴露原 dict）。

    构造：用 GraphExecState.create(graph_id, run_id) 工厂方法；不要直接
    用 dataclass 构造器（_lock 必须 lazy 创建避免跨 event loop 复用）。
    """

    graph_id: int
    run_id: str
    started_at: datetime
    deadline_at: datetime | None = None
    variable_pool: VariablePool = field(default_factory=VariablePool)
    # 节点状态字典：node_id → NodeStatus；只通过 set_status 改
    _node_status: dict[str, NodeStatus] = field(default_factory=dict)
    # 每节点的 NodeRunResult 累积（顺序按完成时间）
    _node_runs: list[Any] = field(default_factory=list)
    _status_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def create(
        cls,
        graph_id: int,
        run_id: str,
        deadline_at: datetime | None = None,
    ) -> GraphExecState:
        return cls(
            graph_id=graph_id,
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            deadline_at=deadline_at,
        )

    async def set_status(self, node_id: str, status: NodeStatus) -> None:
        async with self._status_lock:
            self._node_status[node_id] = status

    async def get_status(self, node_id: str) -> NodeStatus:
        async with self._status_lock:
            return self._node_status.get(node_id, NodeStatus.PENDING)

    async def append_run(self, run: Any) -> None:
        """追加 NodeRunResult；不强类型避免循环 import executor.NodeRunResult"""
        async with self._status_lock:
            self._node_runs.append(run)

    async def status_snapshot(self) -> dict[str, NodeStatus]:
        async with self._status_lock:
            return dict(self._node_status)

    async def runs_snapshot(self) -> list[Any]:
        async with self._status_lock:
            return list(self._node_runs)

    def is_deadline_exceeded(self) -> bool:
        if self.deadline_at is None:
            return False
        return datetime.now(timezone.utc) >= self.deadline_at
