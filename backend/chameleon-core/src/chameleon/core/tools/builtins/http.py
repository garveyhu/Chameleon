"""HTTPTool —— 通用 HTTP GET/POST 工具

参数：
    {
      "method": "GET" | "POST",
      "url": "https://...",
      "headers": {"X-Foo": "bar"},          # 可选
      "params": {"k": "v"},                  # 可选 querystring
      "json": {...},                          # 可选 POST body
      "timeout": 10                           # 可选秒
    }

config（admin 配置）：
    {
      "allowed_url_prefixes": ["https://api.example.com/"],   # 允许的 URL 白名单前缀
      "default_timeout": 10,
      "max_response_bytes": 65536                              # 防爆内存
    }

返回：
    ToolResult(data={"status": 200, "headers": {...}, "body": "..." | {...}})
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from chameleon.core.tools.base import Tool, ToolContext, ToolResult
from chameleon.core.tools.registry import register_tool

_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_BYTES = 65_536


class HTTPTool(Tool):
    tool_key = "http"
    description = "通用 HTTP 请求工具（GET/POST），按白名单 URL 前缀限制"
    default_enabled = True

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                },
                "url": {"type": "string"},
                "headers": {"type": "object"},
                "params": {"type": "object"},
                "json": {"type": "object"},
                "timeout": {"type": "number"},
            },
            "required": ["method", "url"],
        }

    async def run(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        method = str(args.get("method", "GET")).upper()
        url = args["url"]
        if not isinstance(url, str) or not url.startswith(
            ("http://", "https://")
        ):
            return ToolResult(ok=False, error=f"非法 url: {url!r}")

        allowed = self.config.get("allowed_url_prefixes") or []
        if allowed and not any(url.startswith(p) for p in allowed):
            return ToolResult(
                ok=False,
                error=(
                    f"URL 不在白名单内（allowed_url_prefixes={allowed}）"
                ),
            )

        timeout = float(
            args.get("timeout") or self.config.get("default_timeout") or _DEFAULT_TIMEOUT
        )
        max_bytes = int(
            self.config.get("max_response_bytes") or _DEFAULT_MAX_BYTES
        )

        headers = {
            "X-Chameleon-Tool": "http",
            "X-Chameleon-Caller": ctx.caller,
        }
        headers.update(args.get("headers") or {})

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=args.get("params"),
                    json=args.get("json") if method == "POST" else None,
                )
        except httpx.TimeoutException:
            return ToolResult(ok=False, error="请求超时")
        except httpx.RequestError as e:
            return ToolResult(ok=False, error=f"网络错误: {e}")

        body_bytes = resp.content[:max_bytes]
        # 尝试解析为 JSON；否则返字符串截断
        body: Any
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = body_bytes.decode(resp.encoding or "utf-8", errors="replace")
        else:
            body = body_bytes.decode(resp.encoding or "utf-8", errors="replace")

        logger.debug(
            "HTTPTool {} {} -> {} | bytes={}",
            method,
            url,
            resp.status_code,
            len(body_bytes),
        )

        return ToolResult(
            ok=resp.is_success,
            data={
                "status": resp.status_code,
                "headers": dict(resp.headers),
                "body": body,
            },
            error=(
                None
                if resp.is_success
                else f"HTTP {resp.status_code}"
            ),
            meta={
                "url": url,
                "method": method,
                "bytes": len(body_bytes),
            },
        )


register_tool(HTTPTool)
