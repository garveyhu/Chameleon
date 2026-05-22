"""PDF parser（pypdf）"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument


async def parse(source: bytes | str, *, name: str) -> "ParsedDocument":
    from chameleon.api.knowledge.parsers import ParsedDocument

    if isinstance(source, str):
        raise TypeError("pdf parser requires bytes input")

    try:
        from pypdf import PdfReader
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("pypdf not installed; uv add pypdf") from e

    reader = PdfReader(io.BytesIO(source))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    text = "\n\n".join(p for p in pages if p.strip())
    metadata: dict = {
        "page_count": len(reader.pages),
        "name": name,
    }
    if reader.metadata:
        if reader.metadata.title:
            metadata["title"] = str(reader.metadata.title)
        if reader.metadata.author:
            metadata["author"] = str(reader.metadata.author)
    return ParsedDocument(text=text, metadata=metadata)
