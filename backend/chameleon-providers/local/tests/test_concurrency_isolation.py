"""并发隔离（评审12 🔴：零并发验证）—— N 个 agent 在同一事件循环并发运行，验各自的输出 /
预算 / 事件缓冲互不串扰（per-transport 状态 + task-local ContextVar 的隔离正确性）。

每个 fake 模型在 ainvoke 里 await sleep 制造任务交错；若框架有共享可变态（如模块级“当前
transport”被并发覆盖），并发下输出/预算会串扰 → 该测能抓。
"""

from __future__ import annotations

import asyncio

import pytest

from chameleon.providers.local.agentkit_runner import InProcessTransport


class _FakeAI:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls: list = []
        self.usage_metadata = {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}


@pytest.mark.asyncio
async def test_concurrent_agent_runs_isolated():
    async def run_one(i: int):
        t = InProcessTransport(
            agent_key=f"a{i}", bindings={}, slots={}, tool_keys=[], budget=100
        )

        class _M:
            def bind_tools(self, schemas):  # noqa: ANN001
                return self

            async def ainvoke(self, messages):  # noqa: ANN001
                await asyncio.sleep(0.01)  # 让出 → 强制并发任务交错
                return _FakeAI(content=f"done-{i}")

        t.chat_model = lambda *, slot=None, model=None: _M()  # type: ignore[method-assign]
        out: list[str] = []
        async for d in t.run_tool_loop(
            messages=[("user", f"q{i}")], slot="chat", model=None,
            platform_keys=[], local_tools=[], max_steps=2,
        ):
            out.append(d)
        return i, "".join(out), t._budget, len(t.drain())

    n = 8
    results = await asyncio.gather(*[run_one(i) for i in range(n)])

    assert len(results) == n
    for i, out, budget, _events in results:
        assert out == f"done-{i}", f"agent {i} 输出串扰：{out!r}"  # 各得自己的输出，无跨 agent 污染
        assert budget == 90, f"agent {i} 预算未独立扣减：{budget}"  # 各 charge 10 token，独立账本
