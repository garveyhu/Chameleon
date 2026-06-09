"""durable HITL 跨层 scope 契约（真 test-DB 集成）——防 playground/embed 那类 scope 寻址 bug 复发。

bug 史：durable pending 按 scope_ref（=session_id/end_user_id）落 AgentMemory、journal 键含 run_id
（=首跑 request_id）。dev 路径碰巧 session_id==request_id==rid 三位一体才工作；playground/embed 的
会话 session ≠ run_id，曾误用 run_id 当 scope 去 resolve → pending 找不到、resume 静默失败。

本测用**真 DB**让 run_agentkit 的 memory_set 与 resolve_resume 打同一库，断言：
  ① 暂停后 pending 落在 scope_ref（≠ run_id）下；
  ② resolve_resume(按 scope_ref) 命中、返回 call_index + 原始 query + run_id；
  ③ resolve_resume(按 run_id) **找不到**（正是当年的 bug 形态）。
单测/tsc 抓不到这类跨层契约错——只有真 DB 往返能验。
"""

from __future__ import annotations

import sys
import types

import pytest

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.engine.agent.durable import resolve_resume
from chameleon.providers.base.types import AgentDef, InvokeContext
from chameleon.providers.local.agentkit_runner import InProcessTransport, run_agentkit

_MOD = "chameleon._test_hitl_scope.agent"


def _register_agent() -> None:
    if _MOD in sys.modules:
        return

    @agent(key="_t_scope_hitl", name="scope 测试", models=[ModelSlot("chat", "c")], durable=True)
    async def handle(ctx: AgentRun):
        summary = await ctx.complete(user="复述")  # call_index 0（journaled）
        decision = await ctx.ask_human("批准吗？")  # call_index 1（暂停点）
        yield f"{summary}/{decision}"

    mod = types.ModuleType(_MOD)
    mod.handle = handle  # type: ignore[attr-defined]
    handle.__module__ = _MOD
    sys.modules[_MOD] = mod


class _FakeMsg:
    def __init__(self, content: str) -> None:
        self.content = content
        self.tool_calls: list = []
        self.usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}


class _FakeChat:
    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, messages, **kw):  # noqa: ANN001
        return _FakeMsg("操作摘要")


@pytest.mark.asyncio
async def test_pending_scoped_by_scope_ref_not_run_id(monkeypatch):
    monkeypatch.setattr(
        InProcessTransport, "chat_model", lambda self, *, slot=None, model=None: _FakeChat()
    )
    _register_agent()
    # 测试卫生：清本 agent 上轮残留 journal/pending——固定 run_id 跨 run 会命中旧 journal → 重放不
    # 暂停。真实调用 request_id 唯一不会撞，此清理仅为本测可重复跑。
    from sqlalchemy import delete

    from chameleon.data.infra.db import AsyncSessionLocal
    from chameleon.data.models import AgentMemory

    async with AsyncSessionLocal() as _s:
        await _s.execute(delete(AgentMemory).where(AgentMemory.agent_key == "_t_scope_hitl"))
        await _s.commit()
    adef = AgentDef(
        key="_t_scope_hitl", provider="local",
        config={"__agentkit_module__": _MOD, "__agentkit_attr__": "handle"},
    )
    scope = "sess-scope-A"  # durable scope_ref（会话 session）
    run_id = "req-uuid-B"   # journal run_id（per-call request_id），与 scope 故意不同

    ctx = InvokeContext(
        agent_def=adef, input="删除生产库", history=[], app_id="app",
        session_id=scope, request_id=run_id, stream=True, context_vars={},
    )
    events = [e async for e in run_agentkit(ctx)]
    assert any(
        e.type.value == "step" and (e.data or {}).get("name") == "human_input_pending"
        for e in events
    ), "durable agent 应暂停并 emit human_input_pending"

    # ② 按 scope_ref 解析命中（playground/embed 的正确寻址）
    spec = await resolve_resume("_t_scope_hitl", scope)
    assert spec is not None, "按 scope_ref 应能读到 pending"
    assert spec.call_index == 1 and spec.run_id == run_id
    assert spec.query == "删除生产库"  # 原始 query 重放用

    # ③ 按 run_id 解析找不到——正是当年 playground bug 的形态（run_id ≠ scope_ref）
    assert await resolve_resume("_t_scope_hitl", run_id) is None

    # ④ resume 跑完（回填答案，不再暂停）→ pending 必须被清（评审22 C2：否则运营「待人工处理」
    # 列表残留已解决项）。同 scope + journal run_id 重放，complete@0 走 journal、ask@1 取答案。
    resume_ctx = InvokeContext(
        agent_def=adef, input="删除生产库", history=[], app_id="app",
        session_id=scope, request_id=run_id, stream=True,
        context_vars={"_resume_answer": "拒绝", "_resume_call_index": 1},
    )
    deltas = [
        e.data.get("text", "")
        async for e in run_agentkit(resume_ctx)
        if e.type.value == "delta"
    ]
    assert "拒绝" in "".join(deltas), "resume 应续跑完成并产出含人工答案的结果"
    assert await resolve_resume("_t_scope_hitl", scope) is None, "resume 完成后 pending 应被清"
