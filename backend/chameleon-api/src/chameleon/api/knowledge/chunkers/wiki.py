"""Wiki collection chunker —— 按 markdown heading 切，保留 heading path

约定输入：markdown，`#` / `##` / `###` 等 heading 作为切分锚点。
每个 chunk 内容 = 该 heading 段（heading + body 直到下一个同级或更高级 heading）。
meta.heading_path = ["# 章节", "## 子章节"] 路径，方便 retrieve 显示来源。

config:
    {
      "max_chunk_size": 2000,      # 单 chunk 上限，超出再 fixed 切
      "min_heading_level": 1,      # 最小切分 heading 级别（# = 1）
      "max_heading_level": 3       # 最大（## = 2, ### = 3）
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from chameleon.api.knowledge.chunker import split
from chameleon.api.knowledge.chunkers.base import ChunkPayload


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_DEFAULT_MAX_CHUNK = 2000


@dataclass
class _Section:
    level: int
    heading_text: str
    body: str  # heading 行 + 后续内容（直到下个 heading）
    start: int


def chunk_wiki(
    text: str, config: dict[str, Any] | None = None
) -> list[ChunkPayload]:
    cfg = config or {}
    max_size = int(cfg.get("max_chunk_size") or _DEFAULT_MAX_CHUNK)
    min_lvl = int(cfg.get("min_heading_level") or 1)
    max_lvl = int(cfg.get("max_heading_level") or 3)

    if not text or not text.strip():
        return []

    # 1. 找所有 heading 位置
    headings = []
    for m in _HEADING_RE.finditer(text):
        lvl = len(m.group(1))
        if min_lvl <= lvl <= max_lvl:
            headings.append((m.start(), lvl, m.group(2).strip()))

    if not headings:
        # 无 heading → 回退 generic（保留同样语义：长文按 paragraph 切）
        from chameleon.api.knowledge.chunkers.generic import chunk_generic

        return chunk_generic(text, {"mode": "paragraph"})

    # 2. 切段：每个 heading 一个 section，body = 当前 heading 到下个 heading 之间
    sections: list[_Section] = []
    for i, (pos, lvl, heading_text) in enumerate(headings):
        body_end = (
            headings[i + 1][0] if i + 1 < len(headings) else len(text)
        )
        body = text[pos:body_end].strip()
        sections.append(_Section(lvl, heading_text, body, pos))

    # 3. 构 heading_path stack + 输出 ChunkPayload
    path_stack: list[str] = []
    out: list[ChunkPayload] = []
    seq = 0
    for sec in sections:
        # 维护 path 栈：当前 section level >= stack top level 时 pop 直到 < 当前
        while path_stack and _level_of(path_stack[-1]) >= sec.level:
            path_stack.pop()
        path_stack.append(f"{'#' * sec.level} {sec.heading_text}")
        heading_path = list(path_stack)

        # body 超长 → 再 fixed 切
        if len(sec.body) <= max_size:
            out.append(
                ChunkPayload(
                    content=sec.body,
                    index_name="chunk",
                    meta={"heading_path": heading_path, "seq": seq},
                )
            )
            seq += 1
        else:
            parts = split(
                sec.body,
                {"mode": "fixed", "chunk_size": max_size, "overlap": 200},
            )
            for p_i, part in enumerate(parts):
                out.append(
                    ChunkPayload(
                        content=part,
                        index_name="chunk",
                        meta={
                            "heading_path": heading_path,
                            "seq": seq,
                            "part": p_i,
                        },
                    )
                )
                seq += 1

    return out


def _level_of(heading_line: str) -> int:
    """从 '## Foo' 提 2"""
    m = re.match(r"^(#+) ", heading_line)
    return len(m.group(1)) if m else 0
