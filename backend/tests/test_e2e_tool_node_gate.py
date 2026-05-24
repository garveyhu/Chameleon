"""P18.2 PR #23: ToolNode 跑时按 tool_instances.enabled 做闸门"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import delete

from chameleon.core.graph import (
    EdgeSpec,
    GraphSpec,
    NodeContext,
    NodeSpec,
)
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import ToolInstance
from datetime import datetime, timezone


@pytest_asyncio.fixture
async def _clean():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ToolInstance))
        await s.commit()


def _ctx() -> NodeContext:
    return NodeContext(
        request_id="rid",
        graph_id=1,
        graph_run_id=1,
        depth=0,
        started_at=datetime.now(timezone.utc),
    )


async def test_tool_node_uses_admin_config_when_enabled(_clean):
    """admin 给 http tool 配 allowed_url_prefixes；ToolNode 跑时拿到该 config"""
    async with AsyncSessionLocal() as s:
        s.add(
            ToolInstance(
                tool_key="http",
                name="public http",
                config={
                    "allowed_url_prefixes": ["https://example.org/"]
                },
                enabled=True,
            )
        )
        await s.commit()

    # 不可达 URL → 应该被白名单拒绝
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(
                id="t",
                type="tool",
                data={
                    "tool_key": "http",
                    "args": {
                        "method": "GET",
                        "url": "https://forbidden.example.com/",
                    },
                },
            ),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="t"),
            EdgeSpec(id="2", source="t", target="e"),
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={}, ctx=_ctx())
    tool_run = next(r for r in result.node_runs if r.node_id == "t")
    assert tool_run.status.value == "success"
    out = tool_run.output
    assert out["ok"] is False
    assert "白名单" in out["error"]


async def test_tool_node_refuses_when_disabled(_clean):
    """admin 把 http 关了 → ToolNode 跑时拒绝"""
    async with AsyncSessionLocal() as s:
        s.add(
            ToolInstance(
                tool_key="http", name="disabled http", config={}, enabled=False
            )
        )
        await s.commit()

    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(
                id="t",
                type="tool",
                data={
                    "tool_key": "http",
                    "args": {"method": "GET", "url": "https://example.com/"},
                },
            ),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="t"),
            EdgeSpec(id="2", source="t", target="e"),
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={}, ctx=_ctx())
    tool_run = next(r for r in result.node_runs if r.node_id == "t")
    out = tool_run.output
    assert out["ok"] is False
    assert "禁用" in out["error"]


async def test_tool_node_works_without_instance(_clean):
    """admin 没配实例 → ToolNode 用代码层默认 config（http 默认无白名单 → 允许所有）"""
    # 真访问无法保证；用一个非法 URL 触发 ok=False
    spec = GraphSpec(
        nodes=[
            NodeSpec(id="s", type="start"),
            NodeSpec(
                id="t",
                type="tool",
                data={
                    "tool_key": "http",
                    "args": {"method": "GET", "url": "not-a-real-url"},
                },
            ),
            NodeSpec(id="e", type="end"),
        ],
        edges=[
            EdgeSpec(id="1", source="s", target="t"),
            EdgeSpec(id="2", source="t", target="e"),
        ],
    )
    executor = Orchestrator(spec)
    result = await executor.run(input={}, ctx=_ctx())
    tool_run = next(r for r in result.node_runs if r.node_id == "t")
    out = tool_run.output
    # 没 instance → 走代码层默认（无白名单）→ URL 校验拒绝（不是 http:// / https:// 开头）
    assert out["ok"] is False
    assert "非法 url" in out["error"]
