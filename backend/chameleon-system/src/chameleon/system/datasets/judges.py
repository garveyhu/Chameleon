"""Eval judges —— 把 (expected, actual) 转 [0, 1] 分数

内置 3 种：
- exact_match：actual_text == expected_text → 1.0；否则 0.0
- contains：expected_text in actual_text → 1.0；否则 0.0
- llm_judge：调 LLM 做软评分（P19 完善；本 PR 占位返 0.5）

调用方契约：
    score = await JUDGES[judge_key](expected, actual)
    score: float | None  （None 表示无法评，比如 expected 缺失）
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable


def _flatten_str(v: Any) -> str:
    """从 dict / str / 其它中抽出可比较的文本"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # 常见字段优先
        for k in ("answer", "text", "content", "value", "output"):
            if isinstance(v.get(k), str):
                return v[k]
        return str(v)
    return str(v)


async def exact_match(expected: Any, actual: Any) -> float | None:
    e = _flatten_str(expected).strip()
    a = _flatten_str(actual).strip()
    if not e:
        return None
    return 1.0 if e == a else 0.0


async def contains(expected: Any, actual: Any) -> float | None:
    e = _flatten_str(expected).strip()
    a = _flatten_str(actual).strip()
    if not e:
        return None
    return 1.0 if e in a else 0.0


async def llm_judge(expected: Any, actual: Any) -> float | None:
    """LLM-as-judge：本 PR 占位（返 0.5）；P19 接入真 prompt + 解析"""
    return 0.5


JUDGES: dict[str, Callable[[Any, Any], Awaitable[float | None]]] = {
    "exact_match": exact_match,
    "contains": contains,
    "llm_judge": llm_judge,
}


def list_judges() -> list[str]:
    return sorted(JUDGES.keys())
