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
