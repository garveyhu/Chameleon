"""一个最小 stdio MCP server（演示/自测用）—— 暴露一个库存查询工具。

被 example-mcp-use agent 经 stdio 启动连接。工具返回的数值无法被模型凭空编造，
用于端到端证明「外部 MCP server 的工具在 ctx.run_with_tools 的 ReAct 循环里被真实调用」。
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("inventory")

_STOCK = {"A100": 42, "B200": 7, "C300": 999}


@mcp.tool()
def lookup_inventory(sku: str) -> dict:
    """查询某 SKU 的当前库存数量。"""
    return {"sku": sku, "quantity": _STOCK.get(sku, 0)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
