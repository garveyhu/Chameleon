"""agentkit working memory 结构化槽真库测试（T1-1 memory 升级 M2）。

验：① ctx.memory.update_working/get_working 跨"会话"持久（按 scope_ref）；② 保留键
__chm_working__ 不污染 ctx.memory.all()、不进语义索引；③ 声明 @agent(working_memory=)
后 run_agentkit 自动把槽当前值渲染进 system（Fake chat 捕获模型实收 messages 验证）。

真 test-DB（不 mock）；chat_model 用 Fake 捕获 system，不打真 LLM。
"""

from __future__ import annotations

import sys
import types

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory, AgentMemoryVector
from chameleon.providers.base.types import AgentDef, InvokeContext
from chameleon.providers.local.agentkit_runner import InProcessTransport, run_agentkit

_AGENT = "_t_working_mem"
_MOD = "chameleon._test_working_mem.agent"


class _Profile(BaseModel):
    name: str = Field(default="", description="用户称呼")
    pref: str = Field(default="", description="回答偏好")


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT))
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


@pytest.mark.asyncio
async def test_update_and_get_working_persist_and_hidden() -> None:
    await _clean()
    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-A")
    run = AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="sess-1", config={},
    )
    out = await run.memory.update_working(name="张三", pref="简洁")
    assert out == {"name": "张三", "pref": "简洁"}

    # 新"会话"（同 scope_ref）能读回 → 跨会话持久
    t2 = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-A")
    run2 = AgentRun(
        transport=t2, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="sess-2", config={},
    )
    assert await run2.memory.get_working() == {"name": "张三", "pref": "简洁"}

    # 保留键不污染 .all()，且不进语义索引集
    assert "__chm_working__" not in await run2.memory.all()
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT)
            )
        ).scalars().all()
    assert all(r.mkey != "__chm_working__" for r in rows)
    await _clean()


class _CapturingChat:
    """ctx.complete 的 Fake：捕获模型实收 messages，返固定文本。"""

    captured: list = []

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, messages, **kw):  # noqa: ANN001
        _CapturingChat.captured.append(messages)

        class _M:
            content = "好的"
            tool_calls: list = []
            usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

        return _M()


def _register_agent() -> None:
    if _MOD in sys.modules:
        return

    @agent(
        key=_AGENT, name="working 测试", models=[ModelSlot("chat", "c")],
        working_memory=_Profile,
    )
    async def handle(ctx: AgentRun):
        ans = await ctx.complete(user=ctx.query)
        yield ans

    mod = types.ModuleType(_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _MOD
    sys.modules[_MOD] = mod


@pytest.mark.asyncio
async def test_working_memory_auto_injected_into_system(monkeypatch) -> None:
    monkeypatch.setattr(
        InProcessTransport, "chat_model",
        lambda self, *, slot=None, model=None: _CapturingChat(),
    )
    _register_agent()
    await _clean()
    _CapturingChat.captured = []

    # 预置 working 槽（模拟上一轮 update_working 写下的事实）
    seed = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="sess-X")
    await AgentRun(
        transport=seed, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="sess-X", config={},
    ).memory.update_working(name="李四", pref="只给代码")

    adef = AgentDef(
        key=_AGENT, provider="local",
        config={"__agentkit_module__": _MOD, "__agentkit_attr__": "handle"},
    )
    ctx = InvokeContext(
        agent_def=adef, input="写个函数", history=[], app_id="app",
        session_id="sess-X", request_id="req-1", stream=True, context_vars={},
    )
    _ = [e async for e in run_agentkit(ctx)]

    assert _CapturingChat.captured, "handle 应触发了一次 ctx.complete"
    sys_msgs = [
        c for msgs in _CapturingChat.captured for (role, c) in msgs if role == "system"
    ]
    blob = "\n".join(sys_msgs)
    assert "关于用户的已知信息" in blob, "working memory 块应注入 system"
    assert "李四" in blob and "只给代码" in blob, "槽当前值应渲染进 system"
    await _clean()
