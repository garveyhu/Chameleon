"""并发隔离（评审12/13）——两个层面：

1. trace/observation ContextVar 跨 asyncio task 的隔离（**真正的共享态风险面**，评审13 指出）：
   _CURRENT_TRACE / _CURRENT_OBS_ID 是进程级 ContextVar，若并发 agent task 间串扰会导致 trace
   归错树 / parent_id 错位。这是 SaaS 多用户并发跑 agent 的真隐患。
2. 多 transport 并发的 liveness + 各自独立账本（per-instance budget/事件缓冲）——较弱（实例本就
   独立），仅作不崩 + 并发 charge 正确的回归护栏。

每个 task 在 set ContextVar 后 await 让出，制造交错；若 ContextVar 未按 task copy-on-write
隔离（如误用全局），交错下断言会失败。
"""

from __future__ import annotations

import asyncio

import pytest

from chameleon.core.observe import (
    TraceContext,
    current_trace_context,
    observe,
    open_trace_scope,
)
from chameleon.providers.local.agentkit_runner import InProcessTransport


class _FakeAI:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls: list = []
        self.usage_metadata = {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}


@pytest.mark.asyncio
async def test_concurrent_trace_scopes_isolated():
    """真并发风险面：N task 各开独立 trace scope + 嵌套 observe，交错 await，断言各自读到的
    trace / observation parent 始终是自己的、不被并发 task 串（_CURRENT_TRACE/_CURRENT_OBS_ID
    跨 task copy-on-write 隔离正确）。"""

    async def flow(i: int):
        async with open_trace_scope(TraceContext(request_id=f"t{i}", channel="test")):
            await asyncio.sleep(0.01)  # 让出：其它 task 在此期间设了各自的 trace
            trace_after_yield = current_trace_context().request_id
            async with observe(observation_type="span", name=f"s{i}", request_id=f"root{i}"):
                await asyncio.sleep(0.01)
                async with observe(observation_type="span", name=f"n{i}") as nested:
                    await asyncio.sleep(0.01)
                    inner_parent = nested.parent_id  # 应继承自己的 root{i}，非并发 task 的
                trace_in_nested = current_trace_context().request_id
        return i, trace_after_yield, trace_in_nested, inner_parent

    results = await asyncio.gather(*[flow(i) for i in range(10)])
    for i, t_after, t_nested, parent in results:
        assert t_after == f"t{i}", f"task {i} trace 被并发串：让出后读到 {t_after}"
        assert t_nested == f"t{i}", f"task {i} trace 嵌套中被串：{t_nested}"
        assert parent == f"root{i}", f"task {i} observation parent 被串：{parent}"


@pytest.mark.asyncio
async def test_concurrent_agent_runs_liveness_and_budget():
    """较弱护栏：N transport 并发跑不崩 + 各自 budget 独立扣减（per-instance 账本）。"""

    async def run_one(i: int):
        t = InProcessTransport(
            agent_key=f"a{i}", bindings={}, slots={}, tool_keys=[], budget=100
        )

        class _M:
            def bind_tools(self, schemas):  # noqa: ANN001
                return self

            async def ainvoke(self, messages):  # noqa: ANN001
                await asyncio.sleep(0.01)
                return _FakeAI(content=f"done-{i}")

        t.chat_model = lambda *, slot=None, model=None: _M()  # type: ignore[method-assign]
        out: list[str] = []
        async for d in t.run_tool_loop(
            messages=[("user", f"q{i}")], slot="chat", model=None,
            platform_keys=[], local_tools=[], max_steps=2,
        ):
            out.append(d)
        return i, "".join(out), t._budget

    results = await asyncio.gather(*[run_one(i) for i in range(8)])
    for i, out, budget in results:
        assert out == f"done-{i}", f"agent {i} 输出串扰：{out!r}"
        assert budget == 90, f"agent {i} 预算未独立扣减：{budget}"
