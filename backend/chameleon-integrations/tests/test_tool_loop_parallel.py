"""run_tool_calls 单轮多工具并行执行（评审6 缺口②：编排原语—并行扇出）。"""

from __future__ import annotations

import asyncio
import time

import pytest

from chameleon.integrations.tools import loop


@pytest.mark.asyncio
async def test_run_tool_calls_parallel_and_ordered(monkeypatch):
    """多 tool_call 并发跑（总耗时≈单个非累加）且输出严格保序。"""

    async def _fake_run_tool(name, args, **_kw):
        await asyncio.sleep(0.15)  # 串行=3×0.15=0.45s；并行≈0.15s
        return {"tool_key": name, "ok": True, "data": f"r-{name}", "error": None}

    monkeypatch.setattr(loop, "run_tool", _fake_run_tool)

    calls = [
        {"name": "t_a", "args": {}, "id": "c1"},
        {"name": "t_b", "args": {}, "id": "c2"},
        {"name": "t_c", "args": {}, "id": "c3"},
    ]
    start = time.monotonic()
    messages, records = await loop.run_tool_calls(calls, caller="test")
    elapsed = time.monotonic() - start

    assert elapsed < 0.35  # 并发：远小于串行 0.45s
    # 严格保序：records / messages 与输入 tool_calls 一一对应
    assert [r["name"] for r in records] == ["t_a", "t_b", "t_c"]
    assert [m.tool_call_id for m in messages] == ["c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_run_tool_calls_per_tool_error_isolated(monkeypatch):
    """单个工具异常收敛成 {ok:False}，不打断其余（并行下仍逐个隔离）。"""

    async def _fake_run_tool(name, args, **_kw):
        if name == "boom":
            raise RuntimeError("炸了")
        return {"tool_key": name, "ok": True, "data": name, "error": None}

    monkeypatch.setattr(loop, "run_tool", _fake_run_tool)
    calls = [
        {"name": "ok1", "args": {}, "id": "1"},
        {"name": "boom", "args": {}, "id": "2"},
        {"name": "ok2", "args": {}, "id": "3"},
    ]
    _messages, records = await loop.run_tool_calls(calls, caller="test")
    assert records[0]["result"]["ok"] is True
    assert records[1]["result"]["ok"] is False  # 失败被收敛，不抛出整轮
    assert records[2]["result"]["ok"] is True


@pytest.mark.asyncio
async def test_run_tool_calls_empty():
    """空 tool_calls → 空结果（不进 gather）。"""
    messages, records = await loop.run_tool_calls([], caller="test")
    assert messages == [] and records == []
