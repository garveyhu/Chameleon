"""Plain text parser"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument


async def parse(source: bytes | str, *, name: str) -> "ParsedDocument":
    from chameleon.api.knowledge.parsers import ParsedDocument

    text = (
        source.decode("utf-8", errors="replace")
        if isinstance(source, bytes)
        else source
    )
    return ParsedDocument(text=text, metadata={"name": name})
