"""retrieval 域 query 扩展（multi-query + HyDE）单测 —— 纯算子，complete_fn 注入 stub。"""

from __future__ import annotations

from chameleon.aikit.tasks.retrieval import expand_queries, hyde_query

# ── expand_queries ──────────────────────────────────────


async def test_expand_queries_parses_lines_and_keeps_original():
    async def complete(_prompt: str) -> str:
        return "1. 变体一\n2) 变体二\n- 变体三"

    out = await expand_queries("原问题", complete_fn=complete, n=3)
    # 原 query 排首位 + 3 个去序号/符号的变体
    assert out[0] == "原问题"
    assert out[1:] == ["变体一", "变体二", "变体三"]


async def test_expand_queries_dedupes_and_caps_to_n():
    async def complete(_prompt: str) -> str:
        return "alpha\nalpha\nbeta\ngamma\ndelta"

    out = await expand_queries("q", complete_fn=complete, n=2)
    # n=2 截断（在去序号后取前 2 个变体）+ 原 query
    assert out[0] == "q"
    assert len(out) == 3  # q + 2 变体
    assert out[1] == "alpha"
    assert out[2] == "beta"


async def test_expand_queries_llm_failure_falls_back_to_original():
    async def boom(_prompt: str) -> str:
        raise RuntimeError("llm down")

    out = await expand_queries("仅此一条", complete_fn=boom, n=3)
    assert out == ["仅此一条"]


async def test_expand_queries_n_zero_returns_original_only():
    async def complete(_prompt: str) -> str:
        return "should-not-be-used"

    out = await expand_queries("q", complete_fn=complete, n=0)
    assert out == ["q"]


async def test_expand_queries_without_original():
    async def complete(_prompt: str) -> str:
        return "v1\nv2"

    out = await expand_queries(
        "q", complete_fn=complete, n=2, include_original=False
    )
    assert out == ["v1", "v2"]


# ── hyde_query ──────────────────────────────────────────


async def test_hyde_returns_hypothetical_answer():
    async def complete(_prompt: str) -> str:
        return "  这是一段假设性答案。  "

    out = await hyde_query("问题", complete_fn=complete)
    assert out == "这是一段假设性答案。"


async def test_hyde_failure_falls_back_to_query():
    async def boom(_prompt: str) -> str:
        raise RuntimeError("timeout")

    assert await hyde_query("原问题", complete_fn=boom) == "原问题"


async def test_hyde_empty_falls_back_to_query():
    async def empty(_prompt: str) -> str:
        return "   "

    assert await hyde_query("原问题", complete_fn=empty) == "原问题"
