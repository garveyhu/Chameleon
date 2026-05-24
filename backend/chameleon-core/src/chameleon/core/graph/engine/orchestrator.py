"""Orchestrator —— 并发图调度主循环（v1.1 PR88b）

设计：
1. 持有 ReadyQueue / WorkerPool / GraphExecState
2. 主循环：从 ReadyQueue.get() 拉 ready node → submit 到 WorkerPool 执行
3. 节点完成时：
   - 写 output 到 VariablePool
   - mark_done(node_id, selected_handle, success)
   - append NodeRunResult 到 state
4. 整图 drained → 返回 RunResult

红线：
- Node API 兼容（execute(ctx, input) 签名不变）
- 节点失败：当前实现直接整图失败（保持现 executor 语义）；continue-on-fail 留 PR89
- 单 input：每个节点只接受一个 incoming 数据流（沿用现 executor 约束）
  - join 节点（多 incoming）：input 是字典 {parent_id: parent_output}，PR89 完善
- if_else 分支：node.selected_branch(output) 返回 'true'/'false'，传给 mark_done
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.engine.ready_queue import ReadyQueue
from chameleon.core.graph.engine.state import GraphExecState
from chameleon.core.graph.engine.worker_pool import WorkerPool
from chameleon.core.graph.node_base import Node, NodeStatus
from chameleon.core.graph.types import GraphSpec, NodeSpec


# 复用 executor.py 的 NodeRunResult / RunResult（避免重复定义）
from chameleon.core.graph.executor import (
    NodeRunResult,
    RunResult,
    _NODE_REGISTRY,
)


class OrchestratorConfig(BaseModel):
    """Orchestrator 运行参数"""

    concurrency: int = Field(default=5, ge=1, le=50)
    node_timeout_seconds: float | None = Field(default=None, gt=0)
    # 整图最大执行秒数；超时由 Orchestrator 主循环检测
    total_timeout_seconds: float | None = Field(default=None, gt=0)


class Orchestrator:
    """并发图执行器

    用法：
        orch = Orchestrator(spec, config=OrchestratorConfig(concurrency=3))
        result = await orch.run(input={"q": "hi"}, ctx=ctx)
    """

    def __init__(
        self,
        spec: GraphSpec,
        *,
        config: OrchestratorConfig | None = None,
        node_factory: Callable[[NodeSpec], Node] | None = None,
    ) -> None:
        self.spec = spec
        self.config = config or OrchestratorConfig()
        self._factory = node_factory or _default_factory
        self._nodes: dict[str, Node] = {
            n.id: self._factory(n) for n in spec.nodes
        }
        # 失败标记：任一节点失败后置 True，主循环停止派发新 task
        self._failed_error: dict[str, Any] | None = None

    async def run(self, *, input: Any, ctx: NodeContext) -> RunResult:
        """跑整张图，返回 RunResult"""
        started_at = datetime.now(timezone.utc)
        deadline = None
        if self.config.total_timeout_seconds:
            deadline = datetime.fromtimestamp(
                started_at.timestamp() + self.config.total_timeout_seconds,
                tz=timezone.utc,
            )
        state = GraphExecState.create(
            graph_id=ctx.graph_id,
            run_id=ctx.request_id,
            deadline_at=deadline,
        )
        # 把 graph input 注入到 start 节点（通过 VariablePool 的"虚拟 parent"）
        await state.variable_pool.set_global("__graph_input__", input)

        rq = ReadyQueue(self.spec)
        pool = WorkerPool(concurrency=self.config.concurrency)

        last_output: Any = None

        # 主循环：拉 ready node → submit
        while not rq.is_drained() and self._failed_error is None:
            if state.is_deadline_exceeded():
                self._failed_error = {
                    "type": "GraphTimeoutError",
                    "message": f"total_timeout_seconds={self.config.total_timeout_seconds} 超时",
                }
                break

            # 拉 ready node；超时 200ms 后检查 in_flight / failed 状态
            try:
                node_id = await asyncio.wait_for(rq.get(), timeout=0.2)
            except asyncio.TimeoutError:
                # 没有 ready node，但可能有 in-flight 在跑 → 继续 loop
                if pool.in_flight == 0:
                    # 既无 ready 又无 in-flight → 图已 drained（防御性 break）
                    break
                continue

            await pool.submit(self._run_node(node_id, ctx, rq, state))

        # 等所有 in-flight 完成
        await pool.drain()

        # 收尾：聚合结果
        node_runs = await state.runs_snapshot()
        # 找 end 节点的 output（最后聚合）
        for n in self.spec.nodes:
            if n.type == "end":
                end_out = await state.variable_pool.get_output(n.id)
                if end_out is not None:
                    last_output = end_out
                    break

        finished_at = datetime.now(timezone.utc)
        if self._failed_error is not None:
            return RunResult(
                status=NodeStatus.FAILED,
                input=input,
                output=None,
                error=self._failed_error,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=_ms(started_at, finished_at),
                node_runs=node_runs,
            )
        return RunResult(
            status=NodeStatus.SUCCESS,
            input=input,
            output=last_output,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_ms(started_at, finished_at),
            node_runs=node_runs,
        )

    async def _run_node(
        self,
        node_id: str,
        ctx: NodeContext,
        rq: ReadyQueue,
        state: GraphExecState,
    ) -> None:
        """单节点 worker：拿 input → execute → 写 output → mark_done"""
        node = self._nodes[node_id]
        await state.set_status(node_id, NodeStatus.RUNNING)
        node_started = datetime.now(timezone.utc)

        # 1) 拿 input：单 parent 取它的 output；无 parent (start) 取 graph_input
        input_val = await self._resolve_input(node_id, state)

        # 2) execute（可选 timeout）
        try:
            if self.config.node_timeout_seconds:
                output = await asyncio.wait_for(
                    node.execute(ctx, input_val),
                    timeout=self.config.node_timeout_seconds,
                )
            else:
                output = await node.execute(ctx, input_val)
        except Exception as exc:  # noqa: BLE001
            node_finished = datetime.now(timezone.utc)
            err = {"type": type(exc).__name__, "message": str(exc)[:500]}
            await state.set_status(node_id, NodeStatus.FAILED)
            await state.append_run(
                NodeRunResult(
                    node_id=node_id,
                    node_type=node.type,
                    status=NodeStatus.FAILED,
                    input=input_val,
                    output=None,
                    error=err,
                    started_at=node_started,
                    finished_at=node_finished,
                    duration_ms=_ms(node_started, node_finished),
                )
            )
            await rq.mark_done(node_id, success=False)
            if self._failed_error is None:
                self._failed_error = err
            logger.exception(
                "graph engine node failed | run={} | node={}",
                ctx.request_id,
                node_id,
            )
            return

        # 3) 成功：写 output + append run + mark_done
        node_finished = datetime.now(timezone.utc)
        await state.variable_pool.set_output(node_id, output)
        await state.set_status(node_id, NodeStatus.SUCCESS)
        await state.append_run(
            NodeRunResult(
                node_id=node_id,
                node_type=node.type,
                status=NodeStatus.SUCCESS,
                input=input_val,
                output=output,
                started_at=node_started,
                finished_at=node_finished,
                duration_ms=_ms(node_started, node_finished),
            )
        )
        # 4) if_else 分支决议
        selected = node.selected_branch(output)
        await rq.mark_done(node_id, selected_handle=selected, success=True)

    async def _resolve_input(self, node_id: str, state: GraphExecState) -> Any:
        """根据 incoming edges 拿 input

        - 无 incoming（start 节点）：返回 graph_input
        - 单 incoming：返回该 parent 的 output
        - 多 incoming（join）：返回 dict {parent_id: parent_output}
        """
        incoming = self.spec.incoming_edges(node_id)
        if not incoming:
            return await state.variable_pool.get_global("__graph_input__")
        if len(incoming) == 1:
            return await state.variable_pool.get_output(incoming[0].source)
        return {
            e.source: await state.variable_pool.get_output(e.source)
            for e in incoming
        }


def _default_factory(spec: NodeSpec) -> Node:
    cls = _NODE_REGISTRY.get(spec.type)
    if cls is None:
        raise ValueError(
            f"未知 node type={spec.type!r}；已注册类型："
            f"{sorted(_NODE_REGISTRY.keys())}"
        )
    return cls(spec)


def _ms(t0: datetime, t1: datetime) -> int:
    return int((t1 - t0).total_seconds() * 1000)
