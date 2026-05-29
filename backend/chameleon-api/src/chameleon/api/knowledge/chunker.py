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

from chameleon.data.utils import tokenizer

_SENTENCE_SEP = re.compile(r"(?<=[。！？!?\.])\s*")
_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_OVERLAP = 100
_DEFAULT_TOKEN_CHUNK_SIZE = 512
_DEFAULT_TOKEN_OVERLAP = 50
_DEFAULT_PARENT_SIZE = 1024
_DEFAULT_CHILD_SIZE = 256

#: 文本清洗用正则（切块前预处理）
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def clean_text(text: str, rules: dict[str, Any] | None) -> str:
    """切块前的文本清洗（对齐 Dify 两个开关）。

    - urls_emails：删除所有 URL 与邮箱
    - whitespace：连续空格/制表符 → 单空格；行首尾空白去除；3+ 连续换行 → 2
      （保留段落边界，paragraph 模式仍可按双换行切）
    """
    if not rules:
        return text
    if rules.get("urls_emails"):
        text = _URL_RE.sub("", text)
        text = _EMAIL_RE.sub("", text)
    if rules.get("whitespace"):
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
    return text


def split(text: str, strategy: dict[str, Any] | None) -> list[str]:
    """按 strategy 切块；strategy=None / 缺字段时退化为 fixed 默认值。

    切块前先按 strategy["clean"] 做文本清洗（见 clean_text）。
    """
    cfg = dict(strategy or {})
    mode = cfg.get("mode") or "fixed"
    text = clean_text(text, cfg.get("clean"))

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

    if mode == "parent_child":
        # 扁平返回 child 列表（预览 / 平铺调用方用）；分层结构见 split_parent_child
        return [
            child for _p, children in _parent_child(text, cfg) for child in children
        ]

    chunk_size = int(cfg.get("chunk_size") or _DEFAULT_CHUNK_SIZE)
    overlap = int(cfg.get("overlap") or _DEFAULT_OVERLAP)

    if mode == "qa":
        # QA 实际在 ingest 时由 LLM 对每个基础块生成问答对；这里按段落返回
        # 「将被 QA 的基础块」供预览（预览不跑 LLM）
        return _merge_and_split(_paragraph(text), chunk_size, overlap, "\n\n")
    if mode == "fixed":
        return _fixed(text, chunk_size, overlap)
    if mode == "paragraph":
        return _merge_and_split(_paragraph(text), chunk_size, overlap, "\n\n")
    if mode == "sentence":
        return _merge_and_split(_sentence(text), chunk_size, overlap, "")
    if mode == "regex":
        sep = cfg.get("separator_regex") or r"\n\n+"
        return _merge_and_split(_regex(text, sep), chunk_size, overlap, "\n")
    raise ValueError(f"unsupported chunk mode: {mode!r}")


def split_parent_child(
    text: str, strategy: dict[str, Any] | None
) -> list[tuple[str, list[str]]]:
    """parent-child 分层切块：返回 [(parent 大块, [child 小块...])]。

    parent 按段落折到 parent_size；每个 parent 再按句子折到 chunk_size（child）。
    切块前按 strategy["clean"] 清洗。
    """
    cfg = dict(strategy or {})
    text = clean_text(text, cfg.get("clean"))
    if not text or not text.strip():
        return []
    return _parent_child(text, cfg)


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


def _merge_and_split(
    segments: list[str], chunk_size: int, overlap: int, joiner: str = "\n"
) -> list[str]:
    """结构化分段（段落 / 句子 / 正则）的合并 + 切分（对齐 Dify）：

    1. 单段超 chunk_size → 先 _fixed 切碎（overlap 在此生效）；
    2. 相邻小段贪心合并，拼接后 ≤ chunk_size 就并到同一块，直到放不下再换块。

    这样 chunk_size 对所有结构化模式都生效：小段被合并到接近上限，
    避免「一段一块」的碎片化（旧 _fold_overflow 只切不合并，小段全部原样输出，
    chunk_size 形同虚设）。joiner 为合并相邻段时的连接符（段落 "\\n\\n"、句子 ""）。
    """
    if chunk_size <= 0:
        return [s for s in segments if s.strip()]
    # 1) 归一化：超长段先切碎，保证每个 piece ≤ chunk_size
    pieces: list[str] = []
    for seg in segments:
        if len(seg) <= chunk_size:
            pieces.append(seg)
        else:
            pieces.extend(_fixed(seg, chunk_size, overlap))
    # 2) 贪心合并相邻 piece 到接近 chunk_size
    out: list[str] = []
    buf = ""
    for p in pieces:
        if not buf:
            buf = p
        elif len(buf) + len(joiner) + len(p) <= chunk_size:
            buf = f"{buf}{joiner}{p}"
        else:
            out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return [c for c in out if c.strip()]


def _parent_child(text: str, cfg: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """parent 按段落折到 parent_size；每个 parent 再按句子折到 chunk_size。"""
    parent_size = int(cfg.get("parent_size") or _DEFAULT_PARENT_SIZE)
    child_size = int(cfg.get("chunk_size") or _DEFAULT_CHILD_SIZE)
    overlap = int(cfg.get("overlap") or 0)
    parents = _merge_and_split(_paragraph(text), parent_size, overlap, "\n\n")
    out: list[tuple[str, list[str]]] = []
    for parent in parents:
        children = _merge_and_split(_sentence(parent), child_size, overlap, "")
        out.append((parent, children or [parent]))
    return out
