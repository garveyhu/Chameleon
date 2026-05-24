"""ReadyQueue —— 入度归零节点入队

调度模型：
1. 构造时按 GraphSpec 算每个节点的入度（incoming edges 数）
2. 入度为 0 的节点立刻入队（一般只有 start）
3. 节点完成（success / skipped）时调 mark_done(node_id)：
   - 遍历该节点所有 outgoing edges
   - 把后继节点入度 -1
   - 若后继入度归 0 → 入队
4. is_drained() 表示队列空 + 无 in-flight → 整图执行完毕

if_else 分支选择由 mark_done(skip_branches=...) 处理：未选中分支的后继节点
直接当 "skipped" 处理（递归往后传播 skip）。

红线：
- 不知道任何 Node 实现细节；只看 GraphSpec 拓扑
- 不写 SSE / DB；纯内存 + asyncio.Queue
- 并发安全（asyncio.Queue 本身线程安全，自己维护的 dict 走 _lock）
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from chameleon.core.graph.types import EdgeSpec, GraphSpec


class ReadyQueue:
    """节点 ready 队列 + 拓扑维护

    构造 + 用法：
        rq = ReadyQueue(spec)
        while not rq.is_drained():
            node_id = await rq.get()
            # ... 跑 node ...
            await rq.mark_done(node_id, selected_handle=None)
    """

    def __init__(self, spec: GraphSpec) -> None:
        self._spec = spec
        # 邻接表：node_id → [(target_id, edge.source_handle)]
        self._adj: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        # 当前剩余入度：node_id → int
        self._remaining_in: dict[str, int] = {}
        # 内部状态锁（保护 _remaining_in 跨 worker 写）
        self._lock = asyncio.Lock()
        # in-flight 计数（拿出队列但还没 mark_done 的节点数）
        self._in_flight = 0
        self._queue: asyncio.Queue[str] = asyncio.Queue()

        self._build_topology()
        self._enqueue_zero_indegree_sync()

    # ── 构造期（同步）─────────────────────────────────────

    def _build_topology(self) -> None:
        for n in self._spec.nodes:
            self._remaining_in[n.id] = 0
        for e in self._spec.edges:
            self._adj[e.source].append((e.target, e.source_handle))
            self._remaining_in[e.target] += 1

    def _enqueue_zero_indegree_sync(self) -> None:
        """构造时立刻把入度 0 的节点同步入队（一般只有 start）

        用 put_nowait —— 此时还没有 worker，队列容量无限。
        """
        for nid, deg in self._remaining_in.items():
            if deg == 0:
                self._queue.put_nowait(nid)

    # ── 运行时（异步）─────────────────────────────────────

    async def get(self) -> str:
        """阻塞拿一个 ready node id；自增 in_flight 计数"""
        node_id = await self._queue.get()
        async with self._lock:
            self._in_flight += 1
        return node_id

    async def mark_done(
        self,
        node_id: str,
        *,
        selected_handle: str | None = None,
        success: bool = True,
    ) -> None:
        """节点完成（成功 / 失败 / skip）后调

        Args:
            node_id: 完成的节点
            selected_handle: 仅 if_else 节点用；'true' / 'false'。其余分支会被 skip。
            success: False 时不传播给下游（图级 fail 由 Orchestrator 处理）。

        if_else 分支处理：
            假设 if_else 出 'true' / 'false' 两边；selected_handle='true' 时
            'false' 分支后继节点直接 skip（递归往后）。
        """
        async with self._lock:
            self._in_flight -= 1
            if self._in_flight < 0:
                # 防御性：理论上不应小于 0
                self._in_flight = 0

        if not success:
            # 失败节点：不传播给下游；让 Orchestrator 决定是否整图失败
            return

        edges = self._adj.get(node_id, [])
        # 区分要传播的后继 vs 要 skip 的后继（if_else 未选中的分支）
        propagate: list[str] = []
        skip_descendants: list[str] = []
        for target, handle in edges:
            if selected_handle is not None and handle is not None and handle != selected_handle:
                skip_descendants.append(target)
            else:
                propagate.append(target)

        # 1) 正常后继：入度 -1，归 0 入队
        for target in propagate:
            await self._decrement_and_maybe_enqueue(target)

        # 2) skip 后继：递归 skip 整条分支（每跳一节点都 mark_done(success=False=skip)）
        for target in skip_descendants:
            await self._propagate_skip(target)

    async def _decrement_and_maybe_enqueue(self, target: str) -> None:
        async with self._lock:
            self._remaining_in[target] -= 1
            ready = self._remaining_in[target] == 0
        if ready:
            await self._queue.put(target)

    async def _propagate_skip(self, node_id: str) -> None:
        """跳过这个节点（标 skipped）并把它的所有出边后继也 skip

        递归实现；图无环（spec validator 保证），无栈溢出风险。
        """
        async with self._lock:
            # 也把 skipped 节点的入度归 0，避免别人 enqueue 它
            self._remaining_in[node_id] = 0

        edges = self._adj.get(node_id, [])
        for target, _handle in edges:
            await self._propagate_skip(target)

    # ── 内省 ─────────────────────────────────────────────

    def is_drained(self) -> bool:
        """队列空 + 无 in-flight = 整图执行完"""
        return self._queue.empty() and self._in_flight == 0

    @property
    def in_flight(self) -> int:
        return self._in_flight

    def remaining_pending(self) -> int:
        """剩余未跑节点数（入度 > 0 + 队列中）

        debug 用；orchestrator 不应依赖。
        """
        return sum(1 for v in self._remaining_in.values() if v > 0) + self._queue.qsize()

    # ── 测试 / 调试辅助 ──────────────────────────────────

    def _peek_queue_size(self) -> int:
        return self._queue.qsize()

    def _peek_remaining_in(self, node_id: str) -> int:
        return self._remaining_in.get(node_id, -1)
