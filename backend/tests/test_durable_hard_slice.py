"""durable 覆盖「难」片真库往返（T1-2）：run_with_tools（粗粒度）。

整个工具循环输出当一个 journal 单元：首跑跑完整循环（LLM + 工具）+ journal 累积文本；重放
**整轮不重跑**——不重调 LLM、不重执行工具（含副作用）。验证主流程（HITL 暂停在 run_with_tools
之后）下 durable agent 用 tools 跑通暂停-恢复、重放零重复计费/副作用。

局限（已文档化）：循环中途崩溃恢复会重跑整轮（粗粒度，fine-grained 细粒度留后续）。

不 mock DB（journal 走真 AgentMemory）；LLM/工具用计数 fake 注入（验是否重执行）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from chameleon.agentkit import AgentRun, tool
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory
from chameleon.providers.local.agentkit_runner import InProcessTransport

_AGENT = "_t_durable_hard"


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


def _durable_run(run_id: str) -> AgentRun:
    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-A")
    return AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="user-A", config={}, durable=True, run_id=run_id,
    )


_crash_exec = {"n": 0}


@tool(name="_t_crash_tool", description="counts executions")
async def _crash_tool() -> dict:
    _crash_exec["n"] += 1
    return {"ok": True}


class _CrashThenFinalChat:
    """跨两次 run 共享调用计数：①出 tool_calls ②循环中途崩溃(raise) ③(恢复)出最终文本。"""

    def __init__(self, state: dict) -> None:
        self.state = state

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, convo, **kw):  # noqa: ANN001
        self.state["n"] += 1
        n = self.state["n"]
        if n == 1:  # step0：出 tool_calls
            class _M:
                tool_calls = [{"name": "_t_crash_tool", "args": {}, "id": "c1"}]
                content = ""
                usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

            return _M()
        if n == 2:  # step1 LLM：工具已执行+journal 后，这里崩溃（非瞬时 → 不重试，传播）
            raise RuntimeError("模拟循环中途崩溃")

        class _F:  # 恢复后 step1 重跑：出最终文本
            tool_calls: list = []
            content = "恢复后的最终答案"
            usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

        return _F()


@pytest.mark.asyncio
async def test_mid_loop_crash_recovery_no_retool(monkeypatch) -> None:
    """fine-grained 核心价值：循环**中途崩溃**后恢复，已完成的工具步不重执行（LangGraph 短板的反例）。

    run1：LLM step0(journal) → 工具执行(journal) → LLM step1 崩溃（工具批已 journal）。
    run2(同 run_id 恢复)：step0/工具批 journal-hit（工具零再执行）→ step1 重跑出最终答案续完。
    """
    await _clean()
    _crash_exec["n"] = 0
    chat_state = {"n": 0}
    chat = _CrashThenFinalChat(chat_state)
    monkeypatch.setattr(
        InProcessTransport, "chat_model",
        lambda self, *, slot=None, model=None: chat,
    )
    rid = "rid-crash-1"

    # run1：崩溃在 step1 LLM（工具已执行 1 次 + journal）
    with pytest.raises(RuntimeError, match="崩溃"):
        async for _ in _durable_run(rid).run_with_tools(user="查天气", tools=[_crash_tool]):
            pass
    assert _crash_exec["n"] == 1, "run1 工具执行一次"
    assert chat_state["n"] == 2, "run1 跑了 step0 + step1(崩溃)"

    # run2：恢复 → step0/工具批 journal-hit（工具零再执行）→ step1 重跑续完
    out = "".join(
        [d async for d in _durable_run(rid).run_with_tools(user="查天气", tools=[_crash_tool])]
    )
    assert out == "恢复后的最终答案"
    assert _crash_exec["n"] == 1, "恢复不应重执行已完成的工具（fine-grained 关键）"
    assert chat_state["n"] == 3, "恢复只重跑崩溃的 step1，step0/工具批走 journal"
    await _clean()


_exec = {"n": 0}


@tool(name="_t_counter_tool", description="counts executions")
async def _counter_tool() -> dict:
    _exec["n"] += 1
    return {"ok": True}


class _ToolThenFinalChat:
    """ainvoke#1 出 tool_calls（触发工具执行），ainvoke#2 出最终文本。"""

    def __init__(self) -> None:
        self.ainvoke_calls = 0

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, convo, **kw):  # noqa: ANN001
        self.ainvoke_calls += 1
        first = self.ainvoke_calls == 1

        class _M:
            tool_calls = (
                [{"name": "_t_counter_tool", "args": {}, "id": "c1"}] if first else []
            )
            content = "" if first else "最终答案"
            usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

        return _M()


@pytest.mark.asyncio
async def test_run_with_tools_tool_not_reexecuted_on_replay(monkeypatch) -> None:
    """端到端：首跑真执行本地工具 + 两轮 LLM；重放零再调 LLM、零再执行工具。"""
    await _clean()
    _exec["n"] = 0
    chat = _ToolThenFinalChat()
    monkeypatch.setattr(
        InProcessTransport, "chat_model",
        lambda self, *, slot=None, model=None: chat,
    )

    rid = "rid-rwt-2"
    out1 = "".join(
        [
            d async for d in _durable_run(rid).run_with_tools(
                user="查天气", tools=[_counter_tool]
            )
        ]
    )
    assert out1 == "最终答案"
    assert chat.ainvoke_calls == 2 and _exec["n"] == 1, "首跑应跑两轮 LLM + 执行工具一次"

    # 重放：journal-hit 一次性吐，零再调 LLM / 零再执行工具
    out2 = "".join(
        [
            d async for d in _durable_run(rid).run_with_tools(
                user="查天气", tools=[_counter_tool]
            )
        ]
    )
    assert out2 == "最终答案"
    assert chat.ainvoke_calls == 2, "重放不应重调 LLM"
    assert _exec["n"] == 1, "重放不应重执行工具（副作用零重复）"
    await _clean()
