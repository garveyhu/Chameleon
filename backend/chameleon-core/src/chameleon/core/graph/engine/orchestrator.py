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
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.engine.event_manager import (
    GraphEventManager,
    GraphNodeEventPayload,
    event_graph_finished,
    event_graph_node_delta,
    event_graph_node_failed,
    event_graph_node_finished,
    event_graph_node_started,
    event_graph_started,
)
from chameleon.core.graph.engine.ready_queue import ReadyQueue
from chameleon.core.graph.engine.state import GraphExecState
from chameleon.core.graph.engine.worker_pool import WorkerPool
from chameleon.core.graph.node_base import (
    DeltaSink,
    HumanInputRequired,
    Node,
    NodeStatus,
)
from chameleon.core.graph.registry import default_factory as _registry_default_factory
from chameleon.core.graph.results import NodeRunResult, RunResult
from chameleon.core.graph.results import duration_ms as _ms
from chameleon.core.graph.types import GraphSpec, NodeSpec
from chameleon.core.observe.context import ObservationType, observe


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
        self._factory = node_factory or _registry_default_factory
        self._nodes: dict[str, Node] = {
            n.id: self._factory(n) for n in spec.nodes
        }
        # 失败标记：任一节点失败后置 True，主循环停止派发新 task
        self._failed_error: dict[str, Any] | None = None
        # 暂停标记（A6）：human_input 节点触发后置非空，主循环停止派发，整图 PAUSED
        self._paused: dict[str, Any] | None = None
        # resume seed（A6）：run() 时填充
        self._seed_outputs: dict[str, Any] = {}

    async def run(
        self,
        *,
        input: Any,
        ctx: NodeContext,
        events: GraphEventManager | None = None,
        seed_outputs: dict[str, Any] | None = None,
    ) -> RunResult:
        """跑整张图，返回 RunResult

        events 非空时：节点 started/finished/failed + 整图 started/finished 事件
        推到 GraphEventManager（供 SSE 流式消费）；events 为 None 时零开销，
        行为与原 batch 模式完全一致。结束时（含异常）保证 events.close()。

        seed_outputs（A6 resume）：{node_id: output} 预置已完成节点输出。命中的
        节点直接重放该输出（不调 execute），其后继照常推进 —— 用于 human_input
        暂停后回填恢复，跳过已跑节点（含被回填的 human_input 节点）。
        """
        self._seed_outputs = seed_outputs or {}
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

        # 系统变量 sys.*（参考 Dify）：任意节点可经 {{#sys.query#}} 引用 / LLM 节点
        # 据此回填对话记忆。优先取 ctx.extra["sys"]，否则从 dict 形 input 派生。
        sys_vars = dict(ctx.extra.get("sys") or {})
        if isinstance(input, dict):
            sys_vars.setdefault("query", input.get("query"))
            sys_vars.setdefault("history", input.get("history"))
        await state.variable_pool.set_global("sys", sys_vars)
        # P5-2 会话变量：{{#conversation.x#}} 跨轮状态（客户端/调用方携带传入）
        await state.variable_pool.set_global(
            "conversation", dict(ctx.extra.get("conversation") or {})
        )

        if events is not None:
            await events.emit(
                event_graph_started(
                    graph_id=ctx.graph_id, run_id=ctx.request_id
                )
            )

        result: RunResult | None = None
        try:
            rq = ReadyQueue(self.spec)
            pool = WorkerPool(concurrency=self.config.concurrency)

            last_output: Any = None

            # 主循环（事件驱动）：派发当前所有 ready node → 等任一 task 完成
            # （可能 enqueue 新 ready）→ 再派发。无固定 sleep / 轮询拖尾。
            # 失败 / 暂停（human_input）均停止派发新节点。
            while self._failed_error is None and self._paused is None:
                if state.is_deadline_exceeded():
                    self._failed_error = {
                        "type": "GraphTimeoutError",
                        "message": f"total_timeout_seconds={self.config.total_timeout_seconds} 超时",
                    }
                    break

                # 派发当前所有 ready node
                while True:
                    try:
                        node_id = rq.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    await pool.submit(
                        self._run_node(node_id, ctx, rq, state, events)
                    )

                # 队列空 + 无 in-flight → 整图执行完
                if rq.is_drained() and pool.in_flight == 0:
                    break

                # 等任一 in-flight task 完成（其 mark_done 可能 enqueue 新 ready）；
                # 有 deadline 时按剩余时间设上界，确保超时可被及时检测
                await pool.wait_any(timeout=self._wait_budget(state))

            # 等所有 in-flight 完成
            await pool.drain()

            # 收尾：聚合结果
            node_runs = await state.runs_snapshot()
            # 节点轨迹落 call_logs span 行（嵌在根 trace 下；无 trace scope 自动跳过）。
            # generation 行已在节点 execute 期间由 GenerationRecorder 按同一确定性 id
            # 挂到对应 span 下 —— 这里补落 span 壳，trace 树即成 LangSmith 层级。
            from chameleon.core.observe.graph_spans import persist_node_spans

            await persist_node_spans(
                root_request_id=ctx.request_id, node_runs=node_runs
            )
            # 找 end 节点的 output（最后聚合）
            for n in self.spec.nodes:
                if n.type == "end":
                    end_out = await state.variable_pool.get_output(n.id)
                    if end_out is not None:
                        last_output = end_out
                        break

            finished_at = datetime.now(timezone.utc)
            # 已完成节点输出快照（resume seed 用）
            outputs_snapshot = (await state.variable_pool.snapshot())["outputs"]
            if self._failed_error is not None:
                result = RunResult(
                    status=NodeStatus.FAILED,
                    input=input,
                    output=None,
                    error=self._failed_error,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_ms(started_at, finished_at),
                    node_runs=node_runs,
                    node_outputs=outputs_snapshot,
                )
            elif self._paused is not None:
                result = RunResult(
                    status=NodeStatus.PAUSED,
                    input=input,
                    output=None,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_ms(started_at, finished_at),
                    node_runs=node_runs,
                    pending=self._paused,
                    node_outputs=outputs_snapshot,
                )
            else:
                result = RunResult(
                    status=NodeStatus.SUCCESS,
                    input=input,
                    output=last_output,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_ms(started_at, finished_at),
                    node_runs=node_runs,
                    node_outputs=outputs_snapshot,
                )
            return result
        finally:
            if events is not None:
                if result is not None:
                    await events.emit(
                        event_graph_finished(
                            status=result.status.value,
                            duration_ms=result.duration_ms,
                            node_count=len(result.node_runs),
                            output=result.output,
                            error=result.error,
                        )
                    )
                await events.close()

    def _wait_budget(self, state: GraphExecState) -> float | None:
        """主循环 wait_any 的超时上界

        无 deadline → None（阻塞到任一 task 完成，无拖尾）；
        有 deadline → 剩余秒数（封顶 1s，保证 deadline 能被及时检测）。
        """
        if state.deadline_at is None:
            return None
        remaining = (state.deadline_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, min(remaining, 1.0))

    async def run_streaming(
        self, *, input: Any, ctx: NodeContext
    ) -> AsyncIterator[dict[str, Any]]:
        """流式跑整张图：边执行边 yield SSE 事件 dict

        producer（run()）在独立 task 里跑，把事件推到 GraphEventManager；
        本协程顺序消费队列并 yield。run() 的 finally 保证 close()，故
        em.stream() 一定能正常结束。run task 的最终结果不在此返回 —— 整图
        摘要随 graph.finished 事件透出（持久化由 GraphRunner service 负责）。

        用法（service 层）：
            orch = Orchestrator(spec)
            return sse_response(orch.run_streaming(input=..., ctx=...))
        """
        em = GraphEventManager()
        run_task = asyncio.create_task(self.run(input=input, ctx=ctx, events=em))
        try:
            async for chunk in em.stream():
                yield chunk
        finally:
            # run() 内部 finally 已 close em；这里只确保 task 收尾、不吞异常日志
            try:
                await run_task
            except Exception:  # noqa: BLE001
                logger.exception(
                    "graph run_streaming: run task 异常 | run={}", ctx.request_id
                )

    async def _run_node(
        self,
        node_id: str,
        ctx: NodeContext,
        rq: ReadyQueue,
        state: GraphExecState,
        events: GraphEventManager | None = None,
    ) -> None:
        """单节点 worker：拿 input → execute → 写 output → mark_done"""
        node = self._nodes[node_id]
        await state.set_status(node_id, NodeStatus.RUNNING)
        node_started = datetime.now(timezone.utc)
        if events is not None:
            await events.emit(
                event_graph_node_started(
                    GraphNodeEventPayload(
                        node_id=node_id,
                        node_type=node.type,
                        name=node.name,
                        status=NodeStatus.RUNNING.value,
                    )
                )
            )

        # 1) 拿 input：单 parent 取它的 output；无 parent (start) 取 graph_input
        input_val = await self._resolve_input(node_id, state)

        # 变量快照注入 ctx.extra["__vars__"]：{sys: {...}, <node_id>: <output>, ...}
        # 供节点解析 {{#sys.query#}} / {{#nodeId.field#}} 引用 + LLM 回填对话记忆。
        snap = await state.variable_pool.snapshot()
        node_vars: dict[str, Any] = {
            "sys": snap["globals"].get("sys") or {},
            "conversation": snap["globals"].get("conversation") or {},
        }
        node_vars.update(snap["outputs"])
        node_ctx = ctx.model_copy(
            update={"extra": {**ctx.extra, "__vars__": node_vars}}
        )

        # A6 resume：命中 seed 直接重放该输出（不调 execute），其后继照常推进
        if node_id in self._seed_outputs:
            output = self._seed_outputs[node_id]
            await self._finish_success(
                node_id, node, input_val, output, node_started, state, rq, events
            )
            return

        # 2) execute（可选 timeout）
        #    流式模式（events 非空）走 execute_stream + delta emit；
        #    非流式默认 execute_stream 直接转 execute，零差异。
        emit: DeltaSink | None = None
        if events is not None:

            async def emit(text: str, _nid: str = node_id) -> None:
                await events.emit(event_graph_node_delta(_nid, text))

        try:
            # 节点执行期间开 span observe：_CURRENT_OBS_ID = f"{root}.{node_id}"，
            # 期间 LLM 节点 .ainvoke() 触发的 GenerationRecorder 落 generation 时
            # 自动认这个 span 当 parent（span 行本身由 run() finally 的
            # persist_node_spans 用同一确定性 id 补落）。
            async with observe(
                observation_type=ObservationType.SPAN,
                name=node.name or node_id,
                request_id=f"{ctx.request_id}.{node_id}",
            ):
                coro = node.execute_stream(node_ctx, input_val, emit)
                if self.config.node_timeout_seconds:
                    output = await asyncio.wait_for(
                        coro, timeout=self.config.node_timeout_seconds
                    )
                else:
                    output = await coro
        except HumanInputRequired as hir:
            # A6 暂停：记 pending，不 mark_done（不传播给下游），整图置 PAUSED
            node_finished = datetime.now(timezone.utc)
            await state.set_status(node_id, NodeStatus.PAUSED)
            await state.append_run(
                NodeRunResult(
                    node_id=node_id,
                    node_type=node.type,
                    status=NodeStatus.PAUSED,
                    input=input_val,
                    output=None,
                    started_at=node_started,
                    finished_at=node_finished,
                    duration_ms=_ms(node_started, node_finished),
                )
            )
            if self._paused is None:
                self._paused = {
                    "node_id": hir.node_id,
                    "prompt": hir.prompt,
                    "schema": hir.schema,
                    "node_input": input_val,
                }
            logger.info(
                "graph engine paused (human input) | run={} | node={}",
                ctx.request_id,
                node_id,
            )
            return
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
            if events is not None:
                await events.emit(
                    event_graph_node_failed(
                        GraphNodeEventPayload(
                            node_id=node_id,
                            node_type=node.type,
                            name=node.name,
                            status=NodeStatus.FAILED.value,
                            duration_ms=_ms(node_started, node_finished),
                            error=err,
                        )
                    )
                )
            logger.exception(
                "graph engine node failed | run={} | node={}",
                ctx.request_id,
                node_id,
            )
            return

        # 3) 成功：写 output + append run + emit finished + mark_done
        await self._finish_success(
            node_id, node, input_val, output, node_started, state, rq, events
        )

    async def _finish_success(
        self,
        node_id: str,
        node: Node,
        input_val: Any,
        output: Any,
        node_started: datetime,
        state: GraphExecState,
        rq: ReadyQueue,
        events: GraphEventManager | None,
    ) -> None:
        """节点成功收尾（正常执行 + seed 重放共用）：写 output / 记录 / 派发后继"""
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
        if events is not None:
            await events.emit(
                event_graph_node_finished(
                    GraphNodeEventPayload(
                        node_id=node_id,
                        node_type=node.type,
                        name=node.name,
                        status=NodeStatus.SUCCESS.value,
                        duration_ms=_ms(node_started, node_finished),
                        output=output,
                    )
                )
            )
        # if_else 分支决议
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


