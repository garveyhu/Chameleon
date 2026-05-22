"""URL fetcher：拉远程内容后转交对应 parser"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument

_HTTP_TIMEOUT = 30.0
_MAX_SIZE = 32 * 1024 * 1024  # 32 MB 兜底


async def fetch_and_parse(url: str, *, name: str | None = None) -> "ParsedDocument":
    """GET url → content+mime → dispatcher.parse"""
    from chameleon.api.knowledge.parsers import parse as dispatch_parse

    async with httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Chameleon/1.0 KB Ingest"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        if len(resp.content) > _MAX_SIZE:
            raise ValueError(
                f"document too large: {len(resp.content)} bytes (max {_MAX_SIZE})"
            )
        mime = resp.headers.get("content-type", "")
        content = resp.content

    parsed = await dispatch_parse(content, name=name or url, mime_type=mime)
    parsed.metadata.setdefault("source_url", url)
    return parsed
