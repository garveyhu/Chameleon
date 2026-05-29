"""Query 扩展 —— Multi-query（PR B1）+ HyDE（PR B2）

纯算子模块：LLM 以 `complete_fn` callable 注入（prompt → completion text），
不依赖 LLM 工厂 / langchain，便于单测注 stub。

两类扩展：
1. expand_queries  —— LLM 把原 query 改写成 N 个语义等价但措辞不同的变体；
   多变体分别召回再 RRF 融合，提升长尾 query 召回率（FastGPT dataset.search 同思路）。
2. hyde_query      —— LLM 先"假设性回答"原问题，用假答案反向 embed 召回；
   假答案与文档同分布，向量更贴近（Gao et al. 2022 HyDE）。

红线：
- ⛔ LLM 失败 / 超时 → fallback 到 [原 query]（绝不让扩展拖垮主检索）
- ⛔ 不在本模块直接调 embedding / vector store（保持纯函数 + 可测）
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger

#: complete_fn 签名：prompt → completion text（由 pipeline 注入真实 LLM）
CompleteFn = Callable[[str], Awaitable[str]]

DEFAULT_MULTI_QUERY_N = 3
#: 单条扩展 query 上限长度（防 LLM 跑飞输出整段）
_MAX_VARIANT_LEN = 256

_MULTI_QUERY_PROMPT = """\
你是检索查询改写器。请把下面的「原始查询」改写成 {n} 个语义等价、\
但措辞 / 角度 / 关键词不同的检索查询，用于提升知识库召回覆盖面。

要求：
- 每行一个查询，不加序号、不加引号、不加解释
- 保持与原查询相同的信息需求，不要扩大或缩小范围
- 用与原始查询相同的语言

原始查询：{query}
"""

_HYDE_PROMPT = """\
请直接写一段「假设性答案」来回答下面的问题，就像你在一篇权威文档里看到的段落。\
不要说"我不知道"或"需要更多信息"，即使不确定也要给出一个看似可信、信息密集的段落。\
只输出这段答案本身，不要任何前后缀。

问题：{query}
"""


def _clean_lines(text: str) -> list[str]:
    """LLM 多行输出 → 去序号 / 引号 / 空行的干净列表"""
    out: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # 去常见前缀：「1. 」「1) 」「- 」「• 」
        for sep in (". ", ") ", "、"):
            if len(line) > 2 and line[0].isdigit() and sep in line[:4]:
                line = line.split(sep, 1)[1].strip()
                break
        line = line.lstrip("-•*").strip().strip("\"'“”‘’")
        if line:
            out.append(line[:_MAX_VARIANT_LEN])
    return out


async def expand_queries(
    query: str,
    *,
    complete_fn: CompleteFn,
    n: int = DEFAULT_MULTI_QUERY_N,
    include_original: bool = True,
) -> list[str]:
    """把 query 改写成 n 个变体

    Args:
        query: 原始查询
        complete_fn: 注入的 LLM 文本补全 callable
        n: 期望生成的变体数（不含原 query）
        include_original: 结果是否包含原 query（默认包含，排首位）

    Returns:
        去重后的 query 列表；LLM 失败时退化为 [query]。
    """
    base = [query] if include_original else []
    if n <= 0:
        return base or [query]

    try:
        raw = await complete_fn(_MULTI_QUERY_PROMPT.format(n=n, query=query))
    except Exception:
        logger.exception("multi-query expand failed | falling back to original")
        return base or [query]

    variants = _clean_lines(raw)
    # 去重（保序）：原 query 优先；变体去重后再 cap 到 n（避免重复占额度）
    seen: set[str] = set()
    out: list[str] = []
    n_variants = 0
    for is_orig, q in [(True, b) for b in base] + [(False, v) for v in variants]:
        key = q.strip().lower()
        if not key or key in seen:
            continue
        if not is_orig:
            if n_variants >= n:
                continue
            n_variants += 1
        seen.add(key)
        out.append(q)
    return out or [query]


async def hyde_query(
    query: str,
    *,
    complete_fn: CompleteFn,
) -> str:
    """生成 HyDE 假设性答案；用它替代 / 补充原 query 做 embed

    失败时 fallback 返回原 query（调用方据此决定是否退化为普通向量检索）。
    """
    try:
        raw = await complete_fn(_HYDE_PROMPT.format(query=query))
    except Exception:
        logger.exception("hyde generate failed | falling back to original query")
        return query
    hypo = (raw or "").strip()
    return hypo or query
