"""HTML parser（selectolax；提取正文 + 标题）"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument

_STRIP_SCRIPT_STYLE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


async def parse(source: bytes | str, *, name: str) -> "ParsedDocument":
    from chameleon.api.knowledge.parsers import ParsedDocument

    raw = (
        source.decode("utf-8", errors="replace")
        if isinstance(source, bytes)
        else source
    )

    title: str | None = None
    text: str

    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(raw)
        # title
        title_node = tree.css_first("title")
        if title_node and title_node.text():
            title = title_node.text().strip()
        # 删 script/style/noscript 后取 body 文本
        for sel in ("script", "style", "noscript"):
            for n in tree.css(sel):
                n.decompose()
        body = tree.body
        text = (body.text(separator="\n") if body else tree.text(separator="\n")) or ""
    except ImportError:
        # 兜底：正则剥 script/style 后简单去标签
        cleaned = _STRIP_SCRIPT_STYLE.sub("", raw)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        text = cleaned
        m = re.search(r"<title>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
        if m:
            title = _WHITESPACE.sub(" ", m.group(1)).strip()

    # 折叠多空白
    lines = [_WHITESPACE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)

    metadata: dict = {"name": name}
    if title:
        metadata["title"] = title
    return ParsedDocument(text=text, metadata=metadata)
