"""example-mcp-use —— MCP 工具助手：消费外部 MCP server 的 tools。

展示 MCP 互操作（旗舰）：`@agent(mcp_servers=[...])` 声明一个外部 MCP server，其 tools
自动进 `ctx.run_with_tools` 的 ReAct 循环，与本地 @tool / 平台工具混用、零样板。本例用
同目录的 mcp_server.py（stdio，库存查询）经 sys.executable 启动连接。
"""

from __future__ import annotations

import sys
from pathlib import Path

from chameleon.agentkit import AgentRun, McpServerConfig, ModelSlot, agent

_MCP_SERVER = str(Path(__file__).parent / "mcp_server.py")


@agent(
    key="example-mcp-use",
    name="MCP 工具助手",
    description="消费外部 MCP server 工具（库存查询）",
    tags=["example", "mcp"],
    models=[ModelSlot("chat", "对话模型")],
    mcp_servers=[
        McpServerConfig(
            name="inv",
            transport="stdio",
            command=sys.executable,
            args=[_MCP_SERVER],
        )
    ],
)
async def handle(ctx: AgentRun):
    async for delta in ctx.run_with_tools(
        slot="chat",
        system="你是库存助手。查询库存请调用 lookup_inventory 工具，按工具返回的数量作答。",
        user=ctx.query,
    ):
        yield delta
