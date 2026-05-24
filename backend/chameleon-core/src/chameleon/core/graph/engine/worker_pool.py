"""WorkerPool —— asyncio.Semaphore 控制并发数 + create_task 调度

设计：
- 一个 Coroutine = 一个 worker（不是预启动 N 个 worker 等任务，而是按需起）
- Semaphore 限制同时 in-flight 的 task 数（默认 5；可配）
- submit() 立刻 spawn task 但 acquire semaphore；释放在 task 完成时

红线：
- 异常不吞：worker raise 时不让整个 pool 死；submit 的调用方决定怎么处理
- drain() 必须 await，否则 task 可能 leak
- 不依赖 asyncio.Queue（用 set 跟踪 in-flight task，因为我们要支持任意完成顺序）

不做的事（留 PR89）：
- 优先级队列（按节点深度优先 / FIFO 切换）
- 动态扩缩 concurrency
- worker 级 timeout（节点级 timeout 由 Orchestrator 套 asyncio.wait_for）
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any


class WorkerPool:
    """有上限并发的 task 池

    用法：
        pool = WorkerPool(concurrency=5)
        await pool.submit(some_coro())
        # ... 任意多次 submit ...
        await pool.drain()   # 等全部完成
    """

    def __init__(self, concurrency: int = 5) -> None:
        if concurrency < 1:
            raise ValueError(f"concurrency must be >= 1, got {concurrency}")
        self._sem = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._concurrency = concurrency

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def in_flight(self) -> int:
        """当前未完成 task 数（含等 semaphore 的）"""
        return len(self._tasks)

    async def submit(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """提交一个 coroutine 调度执行；返回对应 Task

        当 semaphore 满时 acquire 会阻塞；task spawn 之后立刻返回。
        """
        await self._sem.acquire()
        task = asyncio.create_task(self._run_with_release(coro))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _run_with_release(self, coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            return await coro
        finally:
            self._sem.release()

    async def wait_any(self, *, timeout: float | None = None) -> None:
        """等至少一个 in-flight task 完成（无 task 立即返回）

        Orchestrator 主循环用它做事件驱动唤醒：没有 ready node 但有 task 在跑时，
        等任一 task 完成（可能 enqueue 新 ready node）再继续，避免轮询空转 /
        固定 sleep 拖尾。timeout 用于配合整图 deadline。
        """
        if not self._tasks:
            return
        await asyncio.wait(
            set(self._tasks),
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def drain(self) -> None:
        """等所有 in-flight task 完成（异常不抛，由 task 自己处理）"""
        if not self._tasks:
            return
        # snapshot；新提交的 task 这里不等（drain 后不该再 submit）
        snapshot = list(self._tasks)
        await asyncio.gather(*snapshot, return_exceptions=True)
