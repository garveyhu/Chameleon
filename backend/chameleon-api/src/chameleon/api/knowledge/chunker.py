"""多策略 chunker（P16-C3.2 + P17-D1 token + v1.1 B4 sentence_token）

六种模式：
- fixed          字符级窗口切（chunk_size + overlap）
- paragraph      双换行切，单段超长再 fixed 再切
- sentence       按中英文句号 / 问号 / 感叹号切，单句超长再 fixed
- regex          用户给 separator_regex，单段超长再 fixed
- token          模型感知 token 窗口切（裸滑窗），chunk_size / overlap 单位为 token
- sentence_token 句子边界 + token 预算贪心打包（B4：不割裂句子，碎片化率更低）

策略契约（dict）：
    {
      "mode": "fixed" | "paragraph" | "sentence" | "regex" | "token" | "sentence_token",
      "chunk_size": 800,
      "overlap": 100,
      "separator_regex": "\\n\\n+",   # regex 模式必填
      "model": "gpt-4o-mini",          # token / sentence_token 模式可选；默认 cl100k_base
    }

token 单位说明：token / sentence_token 模式下 chunk_size / overlap 以 token 计。
"""

from __future__ import annotations

import re
from typing import Any

from chameleon.core.utils import tokenizer

_SENTENCE_SEP = re.compile(r"(?<=[。！？!?\.])\s*")
_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_OVERLAP = 100
_DEFAULT_TOKEN_CHUNK_SIZE = 512
_DEFAULT_TOKEN_OVERLAP = 50


def split(text: str, strategy: dict[str, Any] | None) -> list[str]:
    """按 strategy 切块；strategy=None / 缺字段时退化为 fixed 默认值。"""
    cfg = dict(strategy or {})
    mode = cfg.get("mode") or "fixed"

    if not text or not text.strip():
        return []

    if mode in ("token", "sentence_token"):
        token_size = int(cfg.get("chunk_size") or _DEFAULT_TOKEN_CHUNK_SIZE)
        token_overlap = int(cfg.get("overlap") or _DEFAULT_TOKEN_OVERLAP)
        model = cfg.get("model")
        if mode == "token":
            return tokenizer.split_by_tokens(
                text, chunk_tokens=token_size, overlap=token_overlap, model=model
            )
        return tokenizer.chunk_by_sentence(
            text, max_tokens=token_size, overlap_tokens=token_overlap, model=model
        )

    chunk_size = int(cfg.get("chunk_size") or _DEFAULT_CHUNK_SIZE)
    overlap = int(cfg.get("overlap") or _DEFAULT_OVERLAP)

    if mode == "fixed":
        return _fixed(text, chunk_size, overlap)
    if mode == "paragraph":
        return _fold_overflow(_paragraph(text), chunk_size, overlap)
    if mode == "sentence":
        return _fold_overflow(_sentence(text), chunk_size, overlap)
    if mode == "regex":
        sep = cfg.get("separator_regex") or r"\n\n+"
        return _fold_overflow(_regex(text, sep), chunk_size, overlap)
    raise ValueError(f"unsupported chunk mode: {mode!r}")


# ── 各模式 ─────────────────────────────────────────────────


def _fixed(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        return [text]
    if overlap < 0 or overlap >= chunk_size:
        overlap = 0
    step = chunk_size - overlap
    n = len(text)
    out: list[str] = []
    i = 0
    while i < n:
        out.append(text[i : i + chunk_size])
        i += step
    return [c for c in out if c.strip()]


def _paragraph(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]


def _sentence(text: str) -> list[str]:
    pieces = _SENTENCE_SEP.split(text)
    return [s.strip() for s in pieces if s.strip()]


def _regex(text: str, separator: str) -> list[str]:
    try:
        return [p.strip() for p in re.split(separator, text) if p.strip()]
    except re.error as e:
        raise ValueError(f"invalid separator_regex: {separator!r} ({e})") from e


def _fold_overflow(
    segments: list[str], chunk_size: int, overlap: int
) -> list[str]:
    """段落 / 句子结果里：单段超长 → 再 fixed 切；正常段直接保留。"""
    out: list[str] = []
    for seg in segments:
        if len(seg) <= chunk_size:
            out.append(seg)
        else:
            out.extend(_fixed(seg, chunk_size, overlap))
    return out
