"""MCP server（Phase B）单测：平台工具暴露 + 执行经 run_tool。"""

from __future__ import annotations

import json

import pytest

from chameleon.api.mcp_server import (
    build_mcp_server,
    exec_platform_tool,
    list_platform_tools,
)


def test_list_platform_tools_exposes_registry():
    tools = list_platform_tools()
    names = {t["name"] for t in tools}
    # 平台内置工具应被暴露（http/sql/code-runner 启动期已注册）
    assert "http" in names
    for t in tools:
        assert "inputSchema" in t and isinstance(t["inputSchema"], dict)
        assert t["inputSchema"].get("type") == "object"


def test_list_agent_tools_exposes_registered_agents(monkeypatch):
    """已注册 agent 暴露成 agent.<key> MCP 工具（评审3：互操作入场券另一半，#23）。"""
    from chameleon.api.mcp_server import server as srv

    class _Adef:
        name = "示例机器人"

    import chameleon.providers.base as pb

    monkeypatch.setattr(pb, "AGENTS", {"my-bot": _Adef()})
    tools = srv.list_agent_tools()
    names = {t["name"] for t in tools}
    assert "agent.my-bot" in names
    t = next(x for x in tools if x["name"] == "agent.my-bot")
    assert t["inputSchema"]["required"] == ["query"]
    assert "示例机器人" in t["description"]


@pytest.mark.asyncio
async def test_exec_platform_tool_returns_json_via_run_tool():
    # http 工具未配 URL 会失败，但应得到结构化 JSON（ok/error），不抛
    out = await exec_platform_tool("http", {"url": "not-a-url"})
    parsed = json.loads(out)
    assert parsed["tool_key"] == "http"
    assert "ok" in parsed


def test_build_mcp_server_constructs():
    server = build_mcp_server()
    assert server.name == "chameleon"
