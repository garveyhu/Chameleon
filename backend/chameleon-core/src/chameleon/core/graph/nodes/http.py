"""HttpNode —— 外部 HTTP 请求节点（对齐 Dify HTTP 节点）

data:
    method: GET / POST / PUT / DELETE / PATCH（默认 GET）
    url: str（支持 {{#sys.query#}} / {{#nodeId.field#}} 引用）
    headers: dict[str, str]（值支持引用）
    body: str | dict（支持引用；dict 走 JSON）
    timeout_seconds: int（默认 30，cap 120）
    allow_private: bool（默认 False；放行内网/环回地址，SSRF 风险自负）
输出 {"status_code", "body"(json 或 text), "headers"}。

红线（SSRF）：默认拒绝环回 / 私网 / 链路本地地址；admin 显式 allow_private 才放行。
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type
from chameleon.core.graph.variables import resolve_in_text

_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
_TIMEOUT_CAP = 120


def _is_private_host(host: str) -> bool:
    """host 是否指向内网/环回（SSRF 粗筛；非 IP 字面量按域名名单粗判）"""
    h = host.lower().strip("[]")
    if h in {"localhost", "0.0.0.0", ""} or h.endswith((".internal", ".local")):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return (
            ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
        )
    except ValueError:
        return False  # 域名：不在此层解析（保持轻量）；如需严防由网络层兜


class HttpNode(Node[Any, dict]):
    """HTTP 请求节点（type='http'）"""

    type = "http"

    def validate_data(self, data: dict[str, Any]) -> None:
        method = str(data.get("method") or "GET").upper()
        if method not in _ALLOWED_METHODS:
            raise ValueError(f"HttpNode.data.method 必须 ∈ {_ALLOWED_METHODS}")
        if not isinstance(data.get("url"), str) or not data["url"].strip():
            raise ValueError("HttpNode.data.url 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        data = self.spec.data
        method = str(data.get("method") or "GET").upper()
        url = resolve_in_text(data["url"], node_vars)
        timeout = min(int(data.get("timeout_seconds") or 30), _TIMEOUT_CAP)
        allow_private = bool(data.get("allow_private"))

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"HttpNode：仅支持 http/https，得到 {parsed.scheme!r}")
        if not allow_private and _is_private_host(parsed.hostname or ""):
            raise ValueError(
                f"HttpNode：拒绝访问内网/环回地址 {parsed.hostname!r}"
                "（如确需，设 data.allow_private=true）"
            )

        headers = {
            str(k): resolve_in_text(str(v), node_vars)
            for k, v in (data.get("headers") or {}).items()
        }

        req_kwargs: dict[str, Any] = {"headers": headers}
        body = data.get("body")
        if body is not None and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, dict):
                req_kwargs["json"] = json.loads(resolve_in_text(json.dumps(body), node_vars))
            else:
                req_kwargs["content"] = resolve_in_text(str(body), node_vars)

        logger.debug("HttpNode {} | {} {}", self.id, method, url)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            resp = await cli.request(method, url, **req_kwargs)

        try:
            parsed_body: Any = resp.json()
        except (ValueError, json.JSONDecodeError):
            parsed_body = resp.text

        return {
            "status_code": resp.status_code,
            "body": parsed_body,
            "headers": dict(resp.headers),
        }


register_node_type(HttpNode)
