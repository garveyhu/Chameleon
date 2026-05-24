"""tiktoken 封装 —— token 计数 / 编解码 / token 窗口切 / 句子级 token 打包

全局唯一的 token 工具点（chunker / retrieval / 统计共用），懒加载 tiktoken：
未触发 token 功能则零开销。model → 编码器映射带 LRU 缓存。

为什么需要句子级 token 打包（chunk_by_sentence）：
裸 token 窗口切（split_by_tokens）会在词 / 句中间硬切，产生语义破碎的 chunk；
按句子边界打包到 token 预算内，既控长度又不割裂语义，碎片化率显著下降。
"""

from __future__ import annotations

import re
from functools import lru_cache

_DEFAULT_ENCODING = "cl100k_base"

#: 中英文句子边界：
#: - 中文全角终止符 。！？；：后立即切（CJK 通常不带空格）
#: - 英文半角 .!?; 仅在其后跟空白时切（避免割裂 3.14 / e.g. / URL）
#: - 连续空行也算边界
_SENTENCE_SEP = re.compile(r"(?<=[。！？；：])|(?<=[.!?;])(?=\s)|\n{2,}")


@lru_cache(maxsize=16)
def _encoder(model: str | None):
    """按 model 取编码器并缓存；未知 model 落回 cl100k_base（差异 ±5%）"""
    import tiktoken

    if not model:
        return tiktoken.get_encoding(_DEFAULT_ENCODING)
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding(_DEFAULT_ENCODING)


def count_tokens(text: str, *, model: str | None = None) -> int:
    """文本的 token 数（空串 → 0）"""
    if not text:
        return 0
    return len(_encoder(model).encode(text))


def encode(text: str, *, model: str | None = None) -> list[int]:
    return _encoder(model).encode(text or "")


def decode(ids: list[int], *, model: str | None = None) -> str:
    return _encoder(model).decode(ids)


def split_by_tokens(
    text: str,
    *,
    chunk_tokens: int,
    overlap: int = 0,
    model: str | None = None,
) -> list[str]:
    """裸 token 窗口切：编码 → 按 chunk_tokens 滑窗 → 解码回字符串

    overlap >= chunk_tokens / overlap < 0 → overlap 归 0（不抛错）。
    """
    if chunk_tokens <= 0:
        return [text] if text and text.strip() else []
    if overlap < 0 or overlap >= chunk_tokens:
        overlap = 0
    enc = _encoder(model)
    ids = enc.encode(text or "")
    if not ids:
        return []
    step = chunk_tokens - overlap
    out: list[str] = []
    i = 0
    while i < len(ids):
        out.append(enc.decode(ids[i : i + chunk_tokens]))
        i += step
    return [c for c in out if c.strip()]


def split_sentences(text: str) -> list[str]:
    """中英文句子切分（保留句末标点）"""
    if not text or not text.strip():
        return []
    return [s.strip() for s in _SENTENCE_SEP.split(text) if s and s.strip()]


def chunk_by_sentence(
    text: str,
    *,
    max_tokens: int,
    overlap_tokens: int = 0,
    model: str | None = None,
) -> list[str]:
    """句子边界 + token 预算贪心打包

    - 不切断句子，单 chunk token 数尽量贴近且不超过 max_tokens
    - overlap_tokens：下一 chunk 从上一 chunk 末尾回退约 overlap_tokens 的句子开始
    - 超长单句（> max_tokens）→ 退化为 split_by_tokens 切片
    """
    if max_tokens <= 0:
        return [text] if text and text.strip() else []
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        overlap_tokens = 0

    sentences = split_sentences(text)
    if not sentences:
        return []

    sent_tokens = [count_tokens(s, model=model) for s in sentences]

    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0

    def _flush() -> list[str]:
        """落当前 chunk，返回供 overlap 复用的尾部句子"""
        if not cur:
            return []
        chunks.append(" ".join(cur))
        if overlap_tokens <= 0:
            return []
        # 从尾部回退收集 <= overlap_tokens 的句子作为下一 chunk 起点
        tail: list[str] = []
        acc = 0
        for s in reversed(cur):
            t = count_tokens(s, model=model)
            if acc + t > overlap_tokens:
                break
            tail.insert(0, s)
            acc += t
        return tail

    for s, st in zip(sentences, sent_tokens, strict=True):
        if st > max_tokens:
            # 超长单句：先落已累积的，再把这句拆成 token 片
            if cur:
                _flush()
                cur, cur_tokens = [], 0
            chunks.extend(
                split_by_tokens(s, chunk_tokens=max_tokens, overlap=0, model=model)
            )
            continue
        if cur and cur_tokens + st > max_tokens:
            tail = _flush()
            cur = list(tail)
            cur_tokens = sum(count_tokens(x, model=model) for x in cur)
        cur.append(s)
        cur_tokens += st

    if cur:
        chunks.append(" ".join(cur))

    return [c for c in chunks if c.strip()]
