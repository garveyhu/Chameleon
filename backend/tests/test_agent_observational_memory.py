"""observational memory 压缩真库测试（T1-1 memory 升级 M3）。

验：① aikit Observer/Reflector/compress 纯任务（stub LLM，确定性）；② providers/local 后台
压缩落 __chm_observations__（非破坏，合并不删原始）；③ 整合观察自动注入 system（经
_inject_memory_context）；④ 触发门控（短对话不压、长对话才异步触发）。

真 test-DB（不 mock）；LLM 经 complete_fn / monkeypatch 注 stub，不打真模型。
"""

from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import delete, select

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.agentkit._runtime import (
    _OBSERVATIONS_KEY,
    _inject_memory_context,
)
from chameleon.aikit.tasks.memory import compress_observations, observe, reflect
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory, AgentMemoryVector
from chameleon.providers.local import agentkit_runner
from chameleon.providers.local.agentkit_runner import (
    InProcessTransport,
    _compress_memory_bg,
    _extract_conversation_text,
    _maybe_trigger_compression,
)

_AGENT = "_t_obs_mem"


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT))
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


# ── aikit 纯任务（stub LLM） ──────────────────────────────


@pytest.mark.asyncio
async def test_observe_reflect_compress_pure() -> None:
    async def stub(prompt: str) -> str:
        if "对话观察器" in prompt:
            return "用户偏好简洁回答\n用户主用 Python"
        if "画像整合器" in prompt:
            return "用户在北京\n用户偏好简洁回答\n用户主用 Python"
        return ""

    obs = await observe("user: 我喜欢简洁\nassistant: 好的", complete_fn=stub)
    assert "Python" in obs
    merged = await reflect("用户在北京", obs, complete_fn=stub)
    assert "北京" in merged and "Python" in merged
    # 空新观察 → 原样返既有（不丢事实）
    assert await compress_observations("用户在北京", "", complete_fn=stub) == "用户在北京"


# ── providers/local 触发门控 ──────────────────────────────


class _Msg:
    def __init__(self, role: str, text: str) -> None:
        self.role = role
        self._text = text

    def text(self) -> str:
        return self._text


def test_trigger_gating_short_vs_long(monkeypatch) -> None:
    scheduled: list = []
    monkeypatch.setattr(agentkit_runner, "_compress_threshold_chars", lambda: 50)

    # 拦截 create_task 避免真跑后台 LLM；返回带 add_done_callback 的假 task
    import asyncio

    class _FakeTask:
        def add_done_callback(self, _cb) -> None:  # noqa: ANN001
            pass

    def _fake_create_task(coro):  # noqa: ANN001, ANN202
        scheduled.append(coro)
        coro.close()  # 防 "coroutine never awaited"
        return _FakeTask()

    monkeypatch.setattr(asyncio, "create_task", _fake_create_task)

    # 短对话：不触发（门控在 create_task 之前）
    _maybe_trigger_compression(_AGENT, "s", [_Msg("user", "短")])
    assert not scheduled
    # 长对话：触发
    _maybe_trigger_compression(_AGENT, "s", [_Msg("user", "x" * 80)])
    assert len(scheduled) == 1, "长对话应异步触发压缩，短对话不触发"


def test_extract_conversation_text() -> None:
    text = _extract_conversation_text([_Msg("user", "你好"), _Msg("assistant", "在")])
    assert text == "user: 你好\nassistant: 在"


# ── 后台压缩落库 + 自动注入（真库） ──────────────────────


@pytest.mark.asyncio
async def test_compress_bg_persists_and_injects(monkeypatch) -> None:
    await _clean()

    async def fake_compress(existing, conversation, *, complete_fn=None):  # noqa: ANN001, ANN202
        # 合并语义：保留既有 + 追加新观察（非破坏）
        new = "用户主用 Python"
        return f"{existing}\n{new}".strip() if existing else new

    import chameleon.aikit.tasks.memory as memmod

    monkeypatch.setattr(memmod, "compress_observations", fake_compress)

    # 预置既有观察
    seed = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-E")
    await seed.memory_set(_OBSERVATIONS_KEY, "用户在上海")

    await _compress_memory_bg(_AGENT, "user-E", "user: 我用 Python 写后端")

    # ② 落库：整合观察含旧 + 新（非破坏合并）
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                select(AgentMemory).where(
                    AgentMemory.agent_key == _AGENT,
                    AgentMemory.scope_ref == "user-E",
                    AgentMemory.mkey == _OBSERVATIONS_KEY,
                )
            )
        ).scalar_one_or_none()
    assert row is not None
    stored = row.value.get("v")
    assert "用户在上海" in stored and "Python" in stored, "压缩应非破坏合并"

    # 保留键不进语义索引集
    async with AsyncSessionLocal() as s:
        vrows = (
            await s.execute(
                select(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT)
            )
        ).scalars().all()
    assert all(r.mkey != _OBSERVATIONS_KEY for r in vrows)

    # ③ 自动注入：声明 observe_memory 的 agent，run 前 _inject_memory_context 把整合观察渲染进 system
    @agent(key=_AGENT, name="obs 测试", models=[ModelSlot("chat", "c")], observe_memory=True)
    async def handle(ctx: AgentRun):  # noqa: ARG001
        yield "ok"

    mod = "chameleon._test_obs_mem.agent"
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        m.handle = handle  # type: ignore[attr-defined]
        sys.modules[mod] = m

    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-E")
    run = AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="sess", config={},
    )
    await _inject_memory_context(t, handle.__agent_manifest__, run)
    assert "历史对话要点" in run._observations_text
    assert "用户在上海" in run._observations_text and "Python" in run._observations_text

    await _clean()
