"""RAGAS 算子共用 helpers —— P21.2 PR #63

- default_judge_fn：默认 LLM judge（占位实现；P22 接真实 LLM 路径）
- parse_yes_no：从 LLM 回复中抽 yes/no
- jaccard_similarity：词集 Jaccard（answer_relevance 兜底相似度）
"""

from __future__ import annotations

import re


async def default_judge_fn(prompt: str) -> str:
    """默认 judge：占位返 "yes"（保证 builtin 算子能跑出非零分数；
    生产请通过 EvalTemplate.judge_provider 注入真实 LLM judge）。
    """
    _ = prompt
    return "yes"


_YES_RE = re.compile(r"^\s*(yes|true|y|对|是|支持)\b", re.IGNORECASE)
_NO_RE = re.compile(r"^\s*(no|false|n|否|错|不|不支持)\b", re.IGNORECASE)


def parse_yes_no(text: str) -> bool:
    """从 judge 回复中抽 yes/no（unclear 默认 no）"""
    if not text:
        return False
    text = text.strip().lower()
    if _YES_RE.match(text):
        return True
    if _NO_RE.match(text):
        return False
    # 兜底：长文本里 "yes" 早于 "no" 视为 yes
    yes_pos = text.find("yes")
    no_pos = text.find("no")
    if yes_pos < 0 and no_pos < 0:
        return False
    if yes_pos < 0:
        return False
    if no_pos < 0:
        return True
    return yes_pos < no_pos


_WORD_SPLIT = re.compile(r"[\s,。！？.!?;,；、:]+")


def jaccard_similarity(a: str, b: str) -> float:
    """词集 Jaccard 相似度（中英混合按空格 + 标点切；中文按字符也可，简化版按词）"""
    if not a or not b:
        return 0.0
    sa = set(t for t in _WORD_SPLIT.split(a.lower()) if t)
    sb = set(t for t in _WORD_SPLIT.split(b.lower()) if t)
    # 中文兜底：单字也入集（短词时 word split 不够）
    if not sa or len(min(sa, key=len)) > 1:
        sa |= set(c for c in a.lower() if c.strip() and c not in ',.!?。！？')
    if not sb or len(min(sb, key=len)) > 1:
        sb |= set(c for c in b.lower() if c.strip() and c not in ',.!?。！？')
    if not sa or not sb:
        return 0.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0
