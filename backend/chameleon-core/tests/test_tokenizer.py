"""PR B4 单测：core/utils/tokenizer —— token 计数 / 窗口切 / 句子级打包"""

from __future__ import annotations

from chameleon.data.utils import tokenizer

# ── count / encode / decode ─────────────────────────────


def test_count_tokens_empty():
    assert tokenizer.count_tokens("") == 0
    assert tokenizer.count_tokens(None) == 0  # type: ignore[arg-type]


def test_count_tokens_positive():
    assert tokenizer.count_tokens("hello world this is a test") > 0


def test_encode_decode_roundtrip():
    text = "Roundtrip 测试 123"
    ids = tokenizer.encode(text)
    assert tokenizer.decode(ids) == text


def test_unknown_model_falls_back():
    # qwen-plus 不在 tiktoken 已知表 → cl100k_base 兜底，不抛错
    assert tokenizer.count_tokens("abc", model="qwen-plus") > 0


# ── split_by_tokens ─────────────────────────────────────


def test_split_by_tokens_basic():
    text = "word " * 200
    out = tokenizer.split_by_tokens(text, chunk_tokens=30, overlap=5)
    assert len(out) > 1
    assert all(c.strip() for c in out)


def test_split_by_tokens_short_single():
    out = tokenizer.split_by_tokens("tiny", chunk_tokens=100)
    assert len(out) == 1


def test_split_by_tokens_invalid_overlap_disables():
    text = "Hello " * 100
    a = tokenizer.split_by_tokens(text, chunk_tokens=10, overlap=20)
    b = tokenizer.split_by_tokens(text, chunk_tokens=10, overlap=0)
    assert len(a) == len(b)


def test_split_by_tokens_empty():
    assert tokenizer.split_by_tokens("", chunk_tokens=10) == []


# ── split_sentences ─────────────────────────────────────


def test_split_sentences_mixed():
    text = "句一。句二！句三？sentence four. sentence five!"
    out = tokenizer.split_sentences(text)
    assert len(out) >= 5


def test_split_sentences_double_newline():
    out = tokenizer.split_sentences("para one\n\npara two")
    assert len(out) == 2


def test_split_sentences_empty():
    assert tokenizer.split_sentences("   ") == []


# ── chunk_by_sentence ───────────────────────────────────


def test_chunk_by_sentence_packs_within_budget():
    # 10 个短句，每句 ~6 token；预算 30 token → 多句打包成几个 chunk
    sentences = "".join(f"这是第{i}个测试句子。" for i in range(10))
    out = tokenizer.chunk_by_sentence(sentences, max_tokens=30, overlap_tokens=0)
    assert len(out) > 1
    # 每个 chunk 不超预算（含少量编码误差容忍）
    for c in out:
        assert tokenizer.count_tokens(c) <= 30 + 10


def test_chunk_by_sentence_does_not_split_mid_sentence():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    out = tokenizer.chunk_by_sentence(text, max_tokens=8, overlap_tokens=0)
    # 每个 chunk 应由完整句子组成（以句号结尾）
    for c in out:
        assert c.rstrip().endswith(".")


def test_chunk_by_sentence_oversized_single_sentence():
    # 单句超长（无句子边界）→ 退化为 token 窗口切
    long_sentence = "word " * 200  # 无句末标点
    out = tokenizer.chunk_by_sentence(long_sentence, max_tokens=20)
    assert len(out) > 1


def test_chunk_by_sentence_overlap_carries_context():
    text = "".join(f"句子{i}。" for i in range(20))
    no_overlap = tokenizer.chunk_by_sentence(text, max_tokens=20, overlap_tokens=0)
    with_overlap = tokenizer.chunk_by_sentence(text, max_tokens=20, overlap_tokens=8)
    # overlap 会复用尾部句子 → chunk 数 >= 无 overlap
    assert len(with_overlap) >= len(no_overlap)


def test_chunk_by_sentence_empty():
    assert tokenizer.chunk_by_sentence("", max_tokens=100) == []


def test_chunk_by_sentence_low_fragmentation():
    """碎片化率（chunk < 50% 预算）应较低 —— B4 验收口径"""
    text = "".join(f"这是用于测试碎片化率的句子编号{i}，内容稍微长一点。" for i in range(40))
    budget = 60
    out = tokenizer.chunk_by_sentence(text, max_tokens=budget, overlap_tokens=0)
    assert len(out) > 1
    # 除最后一块外，碎片（< 50% 预算）比例 < 10%
    body = out[:-1]
    fragments = sum(1 for c in body if tokenizer.count_tokens(c) < budget * 0.5)
    assert fragments / max(1, len(body)) < 0.10
