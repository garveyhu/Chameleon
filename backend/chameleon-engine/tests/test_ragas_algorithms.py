"""P21.2 PR #63 单测：RAGAS 4 算子 + helpers"""

from __future__ import annotations

import pytest

from chameleon.engine.eval import (
    get_algorithm,
    list_algorithms,
)
from chameleon.engine.eval.algorithms.judge_helpers import (
    jaccard_similarity,
    parse_yes_no,
)

# ── 注册表 ────────────────────────────────────────────────


def test_registry_has_4_ragas_algorithms():
    keys = list_algorithms()
    assert "ragas_faithfulness" in keys
    assert "ragas_answer_relevance" in keys
    assert "ragas_context_precision" in keys
    assert "ragas_context_recall" in keys


def test_get_algorithm_unknown():
    assert get_algorithm("does-not-exist") is None


# ── parse_yes_no ─────────────────────────────────────────


def test_parse_yes_no_basic():
    assert parse_yes_no("yes") is True
    assert parse_yes_no("no") is False
    assert parse_yes_no("YES") is True
    assert parse_yes_no("是") is True
    assert parse_yes_no("否") is False


def test_parse_yes_no_phrase():
    assert parse_yes_no("yes, this is supported") is True
    assert parse_yes_no("no it isn't") is False


def test_parse_yes_no_unclear():
    assert parse_yes_no("") is False
    assert parse_yes_no("maybe") is False  # 无 yes/no 关键词


def test_parse_yes_no_yes_before_no():
    assert parse_yes_no("yes although there is no perfect match") is True


# ── jaccard_similarity ────────────────────────────────────


def test_jaccard_identical():
    assert jaccard_similarity("hello world", "hello world") == pytest.approx(1.0)


def test_jaccard_disjoint():
    assert jaccard_similarity("apple", "banana") < 0.5


def test_jaccard_empty():
    assert jaccard_similarity("", "abc") == 0.0
    assert jaccard_similarity("abc", "") == 0.0


def test_jaccard_chinese_partial():
    s = jaccard_similarity("什么是 RAG", "RAG 是什么")
    assert 0.0 < s <= 1.0


# ── ragas_faithfulness ────────────────────────────────────


async def test_faithfulness_all_supported():
    async def judge(_prompt: str) -> str:
        return "yes"

    algo = get_algorithm("ragas_faithfulness")
    assert algo is not None
    score = await algo(
        question="q",
        answer="句子一。句子二。",
        contexts=["context content"],
        judge_fn=judge,
    )
    assert score == pytest.approx(1.0)


async def test_faithfulness_none_supported():
    async def judge(_prompt: str) -> str:
        return "no"

    algo = get_algorithm("ragas_faithfulness")
    score = await algo(
        question="q",
        answer="句子一。句子二。",
        contexts=["context"],
        judge_fn=judge,
    )
    assert score == 0.0


async def test_faithfulness_empty_answer():
    algo = get_algorithm("ragas_faithfulness")
    score = await algo(
        question="q", answer="", contexts=["c"], judge_fn=None
    )
    assert score == 0.0


async def test_faithfulness_no_contexts():
    algo = get_algorithm("ragas_faithfulness")
    score = await algo(
        question="q", answer="some", contexts=[], judge_fn=None
    )
    assert score == 0.0


# ── ragas_answer_relevance ───────────────────────────────


async def test_answer_relevance_high():
    """judge 反向生成的 question 与原 question 高 jaccard → 高分"""
    async def judge(_prompt: str) -> str:
        return "什么是 RAG"

    algo = get_algorithm("ragas_answer_relevance")
    score = await algo(
        question="什么是 RAG",
        answer="RAG 是检索增强生成",
        contexts=[],
        judge_fn=judge,
        config={"n_questions": 2},
    )
    assert score > 0.5


async def test_answer_relevance_low():
    async def judge(_prompt: str) -> str:
        return "完全无关的另一个问题"

    algo = get_algorithm("ragas_answer_relevance")
    score = await algo(
        question="什么是 RAG",
        answer="some",
        contexts=[],
        judge_fn=judge,
    )
    assert score < 0.5


async def test_answer_relevance_empty():
    algo = get_algorithm("ragas_answer_relevance")
    s = await algo(question="", answer="", contexts=[])
    assert s == 0.0


# ── ragas_context_precision ──────────────────────────────


async def test_context_precision_all_useful():
    async def judge(_prompt: str) -> str:
        return "yes"

    algo = get_algorithm("ragas_context_precision")
    score = await algo(
        question="q",
        answer="a",
        contexts=["chunk1", "chunk2", "chunk3"],
        judge_fn=judge,
    )
    assert score == pytest.approx(1.0)


async def test_context_precision_half_useful():
    flip = iter(["yes", "no", "yes", "no"])

    async def judge(_prompt: str) -> str:
        return next(flip)

    algo = get_algorithm("ragas_context_precision")
    score = await algo(
        question="q",
        answer="a",
        contexts=["c1", "c2", "c3", "c4"],
        judge_fn=judge,
    )
    assert score == pytest.approx(0.5)


async def test_context_precision_no_contexts():
    algo = get_algorithm("ragas_context_precision")
    score = await algo(question="q", answer="a", contexts=[])
    assert score == 0.0


# ── ragas_context_recall ─────────────────────────────────


async def test_context_recall_all_covered():
    async def judge(_prompt: str) -> str:
        return "yes"

    algo = get_algorithm("ragas_context_recall")
    score = await algo(
        question="q",
        answer="a",
        contexts=["context content"],
        ground_truth="GT 句子一。GT 句子二。",
        judge_fn=judge,
    )
    assert score == pytest.approx(1.0)


async def test_context_recall_partial():
    flip = iter(["yes", "no"])

    async def judge(_prompt: str) -> str:
        return next(flip)

    algo = get_algorithm("ragas_context_recall")
    score = await algo(
        question="q",
        answer="a",
        contexts=["c"],
        ground_truth="句一。句二。",
        judge_fn=judge,
    )
    assert score == pytest.approx(0.5)


async def test_context_recall_no_ground_truth():
    algo = get_algorithm("ragas_context_recall")
    score = await algo(
        question="q", answer="a", contexts=["c"], ground_truth=None
    )
    assert score == 0.0


async def test_context_recall_no_contexts():
    algo = get_algorithm("ragas_context_recall")
    score = await algo(
        question="q", answer="a", contexts=[], ground_truth="句子"
    )
    assert score == 0.0
