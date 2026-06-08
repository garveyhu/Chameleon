"""MCP client 连接集成测试 —— 真实 stdio MCP server 端到端（评审4：补旗舰未测的一半）。

覆盖 load_mcp_tools 的真实连接路径：open_session(stdio) → list_tools → 适配 ToolSpec →
handler 调 call_tool → 摊平结果 → aclose。这是 client（双向里更重要的一半）此前零测的
关键路径（test_mcp_adapter.py 只测纯函数 flatten/_make_descriptor，不连真 server）。
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from chameleon.agentkit._mcp import load_mcp_tools

# 极简 stdio MCP server（FastMCP，单工具）—— 写到临时文件经 stdio 拉起
_SERVER_SRC = textwrap.dedent(
    '''
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("calc")

    @mcp.tool()
    def add(a: int, b: int) -> dict:
        """两数相加。"""
        return {"sum": a + b}

    if __name__ == "__main__":
        mcp.run(transport="stdio")
    '''
)


@pytest.mark.asyncio
async def test_load_mcp_tools_connects_real_stdio_server(tmp_path):
    server = tmp_path / "calc_server.py"
    server.write_text(_SERVER_SRC, encoding="utf-8")

    descriptors, stack = await load_mcp_tools(
        [{"name": "calc", "transport": "stdio", "command": sys.executable, "args": [str(server)]}]
    )
    try:
        # 连上真实 server + 列举到 add 工具，schema 来自 inputSchema
        by_name = {d.name: d for d in descriptors}
        assert "add" in by_name
        add = by_name["add"]
        assert add.parameters_schema.get("type") == "object"
        assert "a" in add.parameters_schema.get("properties", {})
        # handler 经 stdio call_tool 真实执行 → 摊平结果
        result = await add.handler(a=3, b=4)
        assert result["ok"] is True
        # structuredContent {"sum":7} 或 text；两种都应含 7
        assert "7" in str(result.get("data"))
    finally:
        await stack.aclose()


@pytest.mark.asyncio
async def test_load_mcp_tools_bad_server_skips_gracefully():
    # 连不上的 server（命令不存在）→ 仅 warning + 返空，不抛
    descriptors, stack = await load_mcp_tools(
        [{"name": "x", "transport": "stdio", "command": "/nonexistent/cmd", "args": []}]
    )
    try:
        assert descriptors == []
    finally:
        await stack.aclose()
