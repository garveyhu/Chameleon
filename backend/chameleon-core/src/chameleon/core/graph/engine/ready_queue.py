"""ReadyQueue —— 入度归零节点入队

调度模型：
1. 构造时按 GraphSpec 算每个节点的入度（incoming edges 数）
2. 入度为 0 的节点立刻入队（一般只有 start）
3. 节点完成（success / skipped）时调 mark_done(node_id)：
   - 遍历该节点所有 outgoing edges
   - 把后继节点入度 -1
   - 若后继入度归 0 → 入队
4. is_drained() 表示队列空 + 无 in-flight → 整图执行完毕

if_else 分支选择由 mark_done(selected_handle=...) 处理：未选中分支的边被
"kill"，沿该边向后传播 skip。

汇聚（OR-join）语义（v1.1 PR A0 修复）：
- 一个节点可能有多条入边（diamond join / if_else 两分支汇聚到 end）。
- 节点 **只要有一条入边是真实完成** 就要执行（OR 语义）；
  只有 **全部入边都被 skip** 时该节点才整体跳过、继续向后传播 skip。
- 纯入度计数（AND-join）无法区分"被 skip 的入边"与"真实完成的入边"，
  所以额外维护 _skipped_in 计数：节点入度归 0 时，若 skipped_in == 入度则
  跳过该节点，否则入队执行。

红线：
- 不知道任何 Node 实现细节；只看 GraphSpec 拓扑
- 不写 SSE / DB；纯内存 + asyncio.Queue
- 并发安全（asyncio.Queue 本身线程安全，自己维护的 dict 走 _lock）
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

from chameleon.core.graph.types import GraphSpec


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
        # 当前剩余入度：node_id → int（真实完成 / skip 的边都会扣减）
        self._remaining_in: dict[str, int] = {}
        # 原始入度（不可变；用于判断"全部入边都被 skip"）
        self._total_in: dict[str, int] = {}
        # 已被 skip 的入边计数：node_id → int
        self._skipped_in: dict[str, int] = defaultdict(int)
        # 内部状态锁（保护 _remaining_in / _skipped_in 跨 worker 写）
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
        self._total_in = dict(self._remaining_in)

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
            selected_handle: 仅 if_else 节点用；'true' / 'false'。未选中 handle 的出边被 kill。
            success: False 时不传播给下游（图级 fail 由 Orchestrator 处理）。

        if_else 分支处理：
            假设 if_else 出 'true' / 'false' 两边；selected_handle='true' 时
            kill 'false' 出边并沿其向后传播 skip。汇聚节点（多入边）只要还有
            真实入边会完成就照常执行，详见模块 docstring 的 OR-join 语义。
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
        for target, handle in edges:
            if (
                selected_handle is not None
                and handle is not None
                and handle != selected_handle
            ):
                # 未选中分支：kill 这条边（沿边向后传播 skip）
                await self._kill_edge_to(target)
            else:
                # 真实完成的边：入度 -1，归 0 入队
                await self._decrement_and_maybe_enqueue(target)

    async def _decrement_and_maybe_enqueue(self, target: str) -> None:
        """一条真实完成的边抵达 target；入度归 0 即入队执行

        因为这条边是真实完成（非 skip），target 必有至少一条真实入边，
        入度归 0 时一定要跑（OR-join：不需要全部入边都真实完成）。
        """
        async with self._lock:
            self._remaining_in[target] -= 1
            ready = self._remaining_in[target] == 0
        if ready:
            await self._queue.put(target)

    async def _kill_edge_to(self, target: str) -> None:
        """一条通往 target 的边被判定不走（if_else 未选中分支）

        入度 -1 且记一次 skip。入度归 0 时：
        - 全部入边都被 skip → target 整体跳过 → 继续 kill 它的所有出边
        - 否则（有真实入边完成过）→ target 仍要执行，入队
        """
        async with self._lock:
            self._remaining_in[target] -= 1
            self._skipped_in[target] += 1
            resolved = self._remaining_in[target] == 0
            all_skipped = self._skipped_in[target] >= self._total_in.get(target, 0)
        if not resolved:
            return
        if all_skipped:
            await self._skip_node(target)
        else:
            await self._queue.put(target)

    async def _skip_node(self, node_id: str) -> None:
        """node_id 整体被跳过：kill 它的所有出边（沿图向后传播 skip）

        递归实现；图无环（spec validator 保证），无栈溢出风险。
        """
        edges = self._adj.get(node_id, [])
        for target, _handle in edges:
            await self._kill_edge_to(target)

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
