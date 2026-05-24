"""Wiki collection chunker —— 按 markdown heading 切，保留 heading path

约定输入：markdown，`#` / `##` / `###` 等 heading 作为切分锚点。
每个 chunk 内容 = 该 heading 段（heading + body 直到下一个同级或更高级 heading）。
meta.heading_path = ["# 章节", "## 子章节"] 路径，方便 retrieve 显示来源。

config:
    {
      "max_chunk_size": 2000,      # 单 chunk 字符上限，超出再 fixed 切
      "min_heading_level": 1,      # 最小切分 heading 级别（# = 1）
      "max_heading_level": 3,      # 最大（## = 2, ### = 3）
      "merge_small": false,        # B4：合并碎片化的小 section（默认关）
      "min_chunk_tokens": 80,      # merge_small 时：token 数低于此的 section 并入相邻
      "model": null                # token 计数用的编码器（默认 cl100k_base）
    }

B4 heading 智能合并（merge_small=true 时启用）：相邻的过小 section（如只有一行
正文的小标题）并入前一个 chunk，降低碎片化率；保留并入前 chunk 的 heading_path。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from chameleon.api.knowledge.chunker import split
from chameleon.api.knowledge.chunkers.base import ChunkPayload
from chameleon.core.utils import tokenizer

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_DEFAULT_MAX_CHUNK = 2000
_DEFAULT_MIN_CHUNK_TOKENS = 80


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
    merge_small = bool(cfg.get("merge_small"))
    min_chunk_tokens = int(cfg.get("min_chunk_tokens") or _DEFAULT_MIN_CHUNK_TOKENS)
    model = cfg.get("model")

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

    if merge_small:
        out = _merge_small_sections(
            out, min_tokens=min_chunk_tokens, max_chars=max_size, model=model
        )
    return out


def _merge_small_sections(
    payloads: list[ChunkPayload],
    *,
    min_tokens: int,
    max_chars: int,
    model: str | None,
) -> list[ChunkPayload]:
    """合并碎片化的小 section（降低 wiki 切块碎片化率）

    - 过小（token < min_tokens）的 section 并入前一个 chunk（前提：合并后不超
      max_chars），保留前 chunk 的 heading_path
    - 首块过小且后面还有块 → 前向并入下一块
    - 不切断已分块的超长 part（带 'part' 字段的不参与并入，避免破坏顺序）
    """
    if len(payloads) <= 1:
        return payloads

    merged: list[ChunkPayload] = []
    for p in payloads:
        is_part = "part" in (p.meta or {})
        too_small = tokenizer.count_tokens(p.content, model=model) < min_tokens
        if (
            merged
            and too_small
            and not is_part
            and len(merged[-1].content) + len(p.content) + 2 <= max_chars
        ):
            prev = merged[-1]
            merged[-1] = replace(prev, content=f"{prev.content}\n\n{p.content}")
        else:
            merged.append(p)

    # 首块过小 → 前向并入下一块（heading_path 取首块的，语义为"章节起点"）
    if (
        len(merged) >= 2
        and "part" not in (merged[0].meta or {})
        and tokenizer.count_tokens(merged[0].content, model=model) < min_tokens
        and len(merged[0].content) + len(merged[1].content) + 2 <= max_chars
    ):
        head, second = merged[0], merged[1]
        merged[1] = replace(
            second,
            content=f"{head.content}\n\n{second.content}",
            meta={**(second.meta or {}), "heading_path": (head.meta or {}).get(
                "heading_path", (second.meta or {}).get("heading_path")
            )},
        )
        merged = merged[1:]

    # 重排 seq（合并后保持连续）
    return [
        replace(p, meta={**(p.meta or {}), "seq": i})
        for i, p in enumerate(merged)
    ]


def _level_of(heading_line: str) -> int:
    """从 '## Foo' 提 2"""
    m = re.match(r"^(#+) ", heading_line)
    return len(m.group(1)) if m else 0
