"""GraphEventManager —— graph 执行期 SSE 事件发射（v1.1 PR A1）

Orchestrator 在节点生命周期（started / finished / failed）和整图生命周期
（graph.started / graph.finished）把 typed 事件 dict 推到一个内部 asyncio.Queue；
service 层通过 `stream()` 边跑边消费，包成 SSE 流给前端。

设计：
- 事件 kind 集中登记在 `chameleon.core.api.sse_events.SSEEventKind`（单一事实来源，
  前端 TS 镜像同一份）；本模块只提供 graph 域的 payload 模型 + 构造 helper。
  红线：禁止匿名 event —— 这里所有构造器都引用 SSEEventKind 成员。
- wire format 与现有 SSE 一致：扁平 dict `{kind: payload}`，由 core/api/sse.py
  的 sse_response 序列化（业务侧只管产 dict 流）。
- 纯内存 + asyncio.Queue；不写 DB / Redis（持久化由 GraphRunner service 负责）。

用法（Orchestrator 内部）：
    em = GraphEventManager()
    await em.emit(event_graph_node_started(GraphNodeEventPayload(node_id="a")))
    ...
    await em.close()           # 推哨兵，stream() 随之结束

用法（service 层消费）：
    async for chunk in em.stream():
        yield chunk            # 交给 sse_response
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict

from chameleon.core.api.sse_events import SSEEventKind

# ── payload 模型 ─────────────────────────────────────────────


class GraphNodeEventPayload(BaseModel):
    """单节点生命周期事件 payload

    started：node_id / node_type / name（status=running）
    finished：+ status=success / duration_ms / output
    failed：+ status=failed / duration_ms / error
    """

    model_config = ConfigDict(extra="allow")

    node_id: str
    node_type: str | None = None
    name: str | None = None
    status: str | None = None  # running / success / failed
    duration_ms: int | None = None
    output: Any = None
    error: dict[str, Any] | None = None


# ── 构造 helper（引用 SSEEventKind，禁止匿名 event）──────────────


def event_graph_started(**fields: Any) -> dict[str, Any]:
    """整图开始 —— 自由字段（graph_id / run_id 等）"""
    return {SSEEventKind.GRAPH_STARTED.value: fields}


def event_graph_node_started(
    payload: GraphNodeEventPayload | dict[str, Any],
) -> dict[str, Any]:
    return {SSEEventKind.GRAPH_NODE_STARTED.value: _dump(payload)}


def event_graph_node_finished(
    payload: GraphNodeEventPayload | dict[str, Any],
) -> dict[str, Any]:
    return {SSEEventKind.GRAPH_NODE_FINISHED.value: _dump(payload)}


def event_graph_node_failed(
    payload: GraphNodeEventPayload | dict[str, Any],
) -> dict[str, Any]:
    return {SSEEventKind.GRAPH_NODE_FAILED.value: _dump(payload)}


def event_graph_finished(
    *,
    status: str,
    duration_ms: int | None = None,
    node_count: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """整图结束 —— status=success / failed，附执行摘要"""
    payload: dict[str, Any] = {"status": status}
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if node_count is not None:
        payload["node_count"] = node_count
    payload.update(extra)
    return {SSEEventKind.GRAPH_FINISHED.value: payload}


def _dump(payload: GraphNodeEventPayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, GraphNodeEventPayload):
        return payload.model_dump(exclude_none=True)
    return payload


# ── 事件队列 ─────────────────────────────────────────────────


class GraphEventManager:
    """graph 执行期事件队列（producer = Orchestrator，consumer = service 层）

    并发模型：多个 worker（节点 task）并发 emit，asyncio.Queue 本身线程安全；
    单一 consumer 通过 stream() 顺序拉取。close() 推 None 哨兵让 stream() 结束。
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._closed = False

    async def emit(self, event: dict[str, Any]) -> None:
        """推一条事件；close 之后再 emit 直接忽略（防御性）"""
        if self._closed:
            return
        await self._queue.put(event)

    async def close(self) -> None:
        """推哨兵，标记流结束（幂等）"""
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """顺序拉取事件，直到收到 close 哨兵"""
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event
