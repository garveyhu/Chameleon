"""chunker 单元测试 —— 含 P17.D1 token 模式"""

from __future__ import annotations

import pytest

from chameleon.api.knowledge import chunker

# ── fixed ─────────────────────────────────────────────────


def test_fixed_chunk_with_overlap():
    text = "abcdefghij" * 10  # 100 chars
    out = chunker.split(text, {"mode": "fixed", "chunk_size": 30, "overlap": 5})
    assert len(out) >= 3
    # 第二块开头应来自第一块的尾部（overlap=5）
    assert out[1].startswith(out[0][-5:])


def test_empty_text_returns_empty():
    assert chunker.split("", {"mode": "fixed"}) == []
    assert chunker.split("   \n  ", {"mode": "fixed"}) == []


def test_default_strategy_falls_back_to_fixed():
    out = chunker.split("hello world", None)
    assert out == ["hello world"]


# ── paragraph / sentence / regex ─────────────────────────


def test_paragraph_mode():
    text = "p1 line1\np1 line2\n\np2 line1\n\np3 only"
    out = chunker.split(text, {"mode": "paragraph", "chunk_size": 500})
    assert len(out) == 3


def test_sentence_mode():
    text = "句一。句二！句三？sentence four. sentence five!"
    out = chunker.split(text, {"mode": "sentence", "chunk_size": 500})
    assert len(out) >= 5


def test_regex_mode():
    text = "a---b---c"
    out = chunker.split(
        text,
        {"mode": "regex", "separator_regex": r"-{3}", "chunk_size": 500},
    )
    assert out == ["a", "b", "c"]


# ── token mode (tiktoken) ─────────────────────────────────


def test_token_mode_default_encoder():
    """无 model 时用 cl100k_base"""
    text = "Hello world, this is a test of token chunking. " * 50
    out = chunker.split(
        text, {"mode": "token", "chunk_size": 30, "overlap": 5}
    )
    assert len(out) > 1
    # 每片解回字符串后非空
    assert all(c.strip() for c in out)


def test_token_mode_known_model():
    """已知 model 取专用编码器"""
    text = "测试中文 token 切分，看看会得到几片。" * 20
    out = chunker.split(
        text,
        {"mode": "token", "chunk_size": 40, "overlap": 10, "model": "gpt-4o-mini"},
    )
    assert len(out) > 1


def test_token_mode_unknown_model_falls_back():
    """未知 model 不抛错，落回 cl100k_base"""
    text = "abcd " * 200
    out = chunker.split(
        text,
        {"mode": "token", "chunk_size": 50, "overlap": 0, "model": "qwen-plus"},
    )
    assert len(out) >= 1


def test_token_mode_short_text_single_chunk():
    out = chunker.split(
        "tiny text", {"mode": "token", "chunk_size": 100, "overlap": 0}
    )
    assert len(out) == 1


def test_token_overlap_validation_disables_when_invalid():
    """overlap >= chunk_size → overlap 自动归 0（不抛错）"""
    text = "Hello " * 100
    out = chunker.split(
        text, {"mode": "token", "chunk_size": 10, "overlap": 20}
    )
    # 应该等价于 overlap=0
    out_ref = chunker.split(
        text, {"mode": "token", "chunk_size": 10, "overlap": 0}
    )
    assert len(out) == len(out_ref)


# ── sentence_token mode (B4) ──────────────────────────────


def test_sentence_token_mode_packs_sentences():
    text = "".join(f"这是第{i}个用于测试的句子。" for i in range(20))
    out = chunker.split(
        text, {"mode": "sentence_token", "chunk_size": 30, "overlap": 0}
    )
    assert len(out) > 1
    assert all(c.strip() for c in out)


def test_sentence_token_mode_keeps_sentences_intact():
    text = "Alpha beta. Gamma delta. Epsilon zeta. Eta theta."
    out = chunker.split(
        text, {"mode": "sentence_token", "chunk_size": 6, "overlap": 0}
    )
    for c in out:
        assert c.rstrip().endswith(".")


def test_sentence_token_short_text_single_chunk():
    out = chunker.split(
        "one short sentence.", {"mode": "sentence_token", "chunk_size": 200}
    )
    assert len(out) == 1


# ── error path ───────────────────────────────────────────


def test_invalid_mode_raises():
    with pytest.raises(ValueError, match="unsupported chunk mode"):
        chunker.split("x", {"mode": "frobnicate"})
