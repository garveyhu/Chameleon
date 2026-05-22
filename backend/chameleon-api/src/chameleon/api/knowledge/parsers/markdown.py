"""Markdown parser（去 fence / 标题保留）"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument

_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


async def parse(source: bytes | str, *, name: str) -> "ParsedDocument":
    from chameleon.api.knowledge.parsers import ParsedDocument

    text = (
        source.decode("utf-8", errors="replace")
        if isinstance(source, bytes)
        else source
    )
    metadata: dict = {"name": name}
    m = _TITLE.search(text)
    if m:
        metadata["title"] = m.group(1).strip()
    return ParsedDocument(text=text, metadata=metadata)
