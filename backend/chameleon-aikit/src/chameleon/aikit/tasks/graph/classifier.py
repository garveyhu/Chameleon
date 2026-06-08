"""意图分类 —— graph classifier 节点的 AI 内核。

纯数据接口：输入 query + 类别表，输出选中的类别 key。prompt 集中在此，
不再行内拼接于节点 execute。
"""

from __future__ import annotations

from typing import Any

from chameleon.aikit.base import LLMRunner

_SYSTEM = "你是意图分类器，只输出一个类别 key，不要多余文字。"
_PROMPT = (
    "把用户问题分到下列类别之一，只输出类别 key（{keys}）：\n"
    "{cat_lines}\n\n问题：{query}"
)


async def classify(
    query: str,
    categories: list[dict[str, Any]],
    *,
    model: str | None = None,
) -> dict[str, str]:
    """把 query 分到 categories 之一。

    Args:
        query: 用户问题文本
        categories: ``[{key, description?}, ...]``（至少 2 个，调用方已校验）
        model: 分类用 LLM code；None 走系统默认

    Returns:
        ``{"category": 选中的 key, "raw": LLM 原始输出}``；无法匹配回落第一个 key
    """
    keys = [str(c["key"]) for c in categories]
    cat_lines = "\n".join(
        f"- {c['key']}: {c.get('description', '')}" for c in categories
    )
    raw = (
        await LLMRunner.run_text(
            _PROMPT.format(keys=" / ".join(keys), cat_lines=cat_lines, query=query),
            model=model,
            system=_SYSTEM,
            retries=0,
        )
    ).strip()
    chosen = (
        next((k for k in keys if k == raw), None)
        or next((k for k in keys if k in raw), None)
        or keys[0]
    )
    return {"category": chosen, "raw": raw}
