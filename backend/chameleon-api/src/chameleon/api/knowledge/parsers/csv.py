"""CSV parser（stdlib）"""

from __future__ import annotations

import csv as _csv
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chameleon.api.knowledge.parsers import ParsedDocument


async def parse(source: bytes | str, *, name: str) -> "ParsedDocument":
    from chameleon.api.knowledge.parsers import ParsedDocument

    if isinstance(source, bytes):
        # 兼容常见编码；BOM 自动剥
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                text = source.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = source.decode("utf-8", errors="replace")
    else:
        text = source

    reader = _csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return ParsedDocument(text="", metadata={"name": name, "row_count": 0})

    header = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    # 把每行拼成 "col1: val1 | col2: val2" 的可读句子，利于 chunk 切句和检索
    lines: list[str] = []
    for r in body:
        pairs = []
        for h, v in zip(header, r):
            v = v.strip()
            if not v:
                continue
            pairs.append(f"{h.strip()}: {v}")
        if pairs:
            lines.append(" | ".join(pairs))
    return ParsedDocument(
        text="\n".join(lines),
        metadata={
            "name": name,
            "row_count": len(body),
            "columns": [h.strip() for h in header],
        },
    )
