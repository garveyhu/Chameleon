"""沙箱墙钟超时 kill 路径真触发（评审12：此前 code-incomplete + test-absent）。

造一个挂死 handle（sleep 远超超时阈值），把 _CHILD_TIMEOUT 调到 2s，断言：
① 不会无限阻塞调用方；② 优雅 StreamEvent.error（"执行超时"）而非裸 TimeoutError；③ 子进程被杀。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

import pytest

import chameleon.providers.local.sandbox.runtime as runtime
from chameleon.providers.base.types import StreamEventType
from chameleon.providers.local.sandbox import run_sandboxed

_HUNG_AGENT = """
import asyncio
from chameleon.agentkit import agent, AgentRun, ModelSlot

@agent(key="_hung_sbx", name="hung", models=[ModelSlot("chat", "c")])
async def handle(ctx: AgentRun):
    await asyncio.sleep(60)   # 远超 _CHILD_TIMEOUT —— 模拟死循环/卡住 handle
    yield "never"
"""


class _Broker:
    def chat_model(self, *, slot=None, model=None):
        return None


@pytest.mark.asyncio
async def test_sandbox_wallclock_timeout_emits_graceful_error(monkeypatch):
    monkeypatch.setattr(runtime, "_CHILD_TIMEOUT", 2.0)  # 缩短墙钟超时便于测
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "_hung_sbx_mod.py"), "w") as f:
        f.write(_HUNG_AGENT)

    events: list = []
    start = time.monotonic()
    async for ev in run_sandboxed(
        module="_hung_sbx_mod", attr="handle", query="hi", broker=_Broker(),
        env_extra={"PYTHONPATH": os.pathsep.join([d, *sys.path])},
    ):
        events.append(ev)
    elapsed = time.monotonic() - start

    # ① 不无限阻塞：~2s 超时 + 杀进程余量，远小于 handle 的 60s sleep
    assert elapsed < 30, f"超时未生效，挂了 {elapsed:.0f}s"
    # ② 优雅 error 事件（非裸 TimeoutError 抛出）
    errs = [e for e in events if e.type == StreamEventType.error]
    assert errs, "超时应 emit error 事件"
    assert "超时" in errs[-1].data.get("message", "")
    # ③ 无正常 delta（handle 从未产出）
    assert not [e for e in events if e.type == StreamEventType.delta]
