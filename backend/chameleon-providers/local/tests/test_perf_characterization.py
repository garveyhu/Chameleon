"""性能特征基准（评审11 缺口：无性能数据）——表征框架开销 + 编排并行 + 沙箱启动成本。

不测 LLM 负载（那受真实模型延迟主导）；测**框架自身**的运营特征，供运营者决策（是否启用
沙箱、扇出是否划算）+ 作回归护栏。零 LLM、零 API 花费。运行看数值：
    pytest test_perf_characterization.py -s
"""

from __future__ import annotations

import asyncio
import textwrap
import time

import pytest

from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.agentkit_runner import InProcessTransport
from chameleon.providers.local.sandbox import run_sandboxed


@pytest.mark.asyncio
async def test_gather_parallel_scaling(monkeypatch, capsys):
    """ctx.gather 并行扇出：N 个各 ~0.1s 的子调用总耗时 ≈ 单个（并行）而非 N×（串行）。"""
    import chameleon.providers.base.a2a_bridge as bridge

    async def _caller(*, source, target, input, trace_id, budget_remaining, depth):
        await asyncio.sleep(0.1)
        return {"answer": f"a-{target}", "tokens": 10}

    monkeypatch.setattr(bridge, "get_a2a_caller", lambda: _caller)
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, request_id="r", budget=100_000)
    n = 6
    start = time.monotonic()
    out = await t.gather([(f"sub{i}", "q") for i in range(n)])
    elapsed = time.monotonic() - start
    with capsys.disabled():
        print(f"\n[perf] gather({n} 分支, 各 0.1s) = {elapsed*1000:.0f}ms（串行需 ~{n*100}ms）")
    assert len(out) == n
    assert elapsed < 0.35  # 并行：远小于串行 0.6s（含调度余量）


@pytest.mark.asyncio
async def test_sandbox_subprocess_overhead(capsys):
    """子进程沙箱启动 + stdio 帧往返开销（运营者据此决策是否对 agent 启用隔离）。"""
    agent_src = textwrap.dedent(
        '''
        from chameleon.agentkit import agent, AgentRun, ModelSlot

        @agent(key="_perf_sbx", name="t", models=[ModelSlot("chat", "c")])
        async def handle(ctx: AgentRun):
            yield "ok"
        '''
    )
    import os
    import sys

    # 写临时 agent 模块（沙箱子进程 import）
    import tempfile

    d = tempfile.mkdtemp()
    with open(os.path.join(d, "_perf_sbx_mod.py"), "w") as f:
        f.write(agent_src)

    class _B:
        def chat_model(self, *, slot=None, model=None):
            return None

    start = time.monotonic()
    deltas = []
    async for ev in run_sandboxed(
        module="_perf_sbx_mod", attr="handle", query="hi", broker=_B(),
        env_extra={"PYTHONPATH": os.pathsep.join([d, *sys.path])},
    ):
        if ev.type == StreamEventType.delta:
            deltas.append(ev.data.get("text", ""))
    elapsed = time.monotonic() - start
    with capsys.disabled():
        print(f"\n[perf] 子进程沙箱启动+往返（trivial agent）= {elapsed*1000:.0f}ms")
    assert "".join(deltas) == "ok"
    assert elapsed < 8.0  # 子进程 spawn + import agentkit + 帧往返的宽松上限（回归护栏）
