"""多策略 chunker（P16-C3.2 + P17-D1 token）

五种模式：
- fixed     字符级窗口切（chunk_size + overlap）
- paragraph 双换行切，单段超长再 fixed 再切
- sentence  按中英文句号 / 问号 / 感叹号切，单句超长再 fixed
- regex     用户给 separator_regex，单段超长再 fixed
- token     模型感知 token 切（tiktoken 编码器），chunk_size / overlap 单位为 token

策略契约（dict）：
    {
      "mode": "fixed" | "paragraph" | "sentence" | "regex" | "token",
      "chunk_size": 800,
      "overlap": 100,
      "separator_regex": "\\n\\n+",   # regex 模式必填
      "model": "gpt-4o-mini",          # token 模式可选；默认 cl100k_base
    }
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

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

    if mode == "token":
        token_size = int(cfg.get("chunk_size") or _DEFAULT_TOKEN_CHUNK_SIZE)
        token_overlap = int(cfg.get("overlap") or _DEFAULT_TOKEN_OVERLAP)
        model = cfg.get("model")
        return _token_split(
            text, model=model, chunk_tokens=token_size, overlap=token_overlap
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


# ── token 模式（tiktoken） ──────────────────────────────────


@lru_cache(maxsize=16)
def _get_encoder(model: str | None):
    """按 model 取编码器并缓存（lazy import tiktoken：未配置 token 模式则零开销）"""
    import tiktoken

    if not model:
        return tiktoken.get_encoding("cl100k_base")
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # 兜底：qwen / claude / 自建模型走 cl100k 近似（差异在 ±5%）
        return tiktoken.get_encoding("cl100k_base")


def _token_split(
    text: str, *, model: str | None, chunk_tokens: int, overlap: int
) -> list[str]:
    """token 级窗口切：先编码→按 chunk_tokens 切片→解码回字符串"""
    if chunk_tokens <= 0:
        return [text]
    if overlap < 0 or overlap >= chunk_tokens:
        overlap = 0
    enc = _get_encoder(model)
    ids = enc.encode(text)
    if not ids:
        return []
    step = chunk_tokens - overlap
    out: list[str] = []
    i = 0
    while i < len(ids):
        piece_ids = ids[i : i + chunk_tokens]
        out.append(enc.decode(piece_ids))
        i += step
    return [c for c in out if c.strip()]
