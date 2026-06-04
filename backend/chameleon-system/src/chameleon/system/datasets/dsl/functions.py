"""DSL 内置评分函数注册表（纯函数，零 LLM、零 IO）。

每个函数签名统一为 (expected_val, actual_val, args) -> float，返回 [1, 5] 量纲分
（二值场景取 5/1）。聚合与归一在 evaluator 层做，本层只出单条字段的原始档分。

量纲约定：5=满足，1=不满足；区分度更细的函数（暂无）也落在 [1, 5] 闭区间。
DSL_FUNCTIONS 是 func 名 → callable 的注册表；未知函数名由 evaluator/parser 处理。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

DslFn = Callable[[Any, Any, dict[str, str]], float]


class DslError(ValueError):
    """DSL 求值 / 解析期的领域异常（未知函数名、参数非法等）。"""


def _as_text(v: Any) -> str:
    """把任意值压成可比较文本：str 原样，None→空串，dict/其它→str()。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _to_float(v: str | None) -> float | None:
    """容错把字符串转 float；失败返 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def fn_exact(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """完全相等（去首尾空白后）返 5，否则 1。"""
    return 5.0 if _as_text(expected).strip() == _as_text(actual).strip() else 1.0


def fn_contains(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """actual 含 expected（子串）返 5，否则 1；expected 为空视为不满足。"""
    e = _as_text(expected).strip()
    if not e:
        return 1.0
    return 5.0 if e in _as_text(actual) else 1.0


def fn_regex(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """actual 匹配 args['pattern'] 返 5，否则 1；pattern 缺失或非法抛 DslError。"""
    pattern = args.get("pattern")
    if not pattern:
        raise DslError("regex 缺少 pattern 参数")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise DslError(f"regex pattern 非法: {pattern!r} ({exc})") from exc
    return 5.0 if compiled.search(_as_text(actual)) else 1.0


def fn_length_gte(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """len(actual) >= args['n'] 返 5，否则 1；n 缺失 / 非数抛 DslError。"""
    n = _to_float(args.get("n"))
    if n is None:
        raise DslError("length_gte 缺少合法 n 参数")
    return 5.0 if len(_as_text(actual)) >= n else 1.0


def fn_length_lte(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """len(actual) <= args['n'] 返 5，否则 1；n 缺失 / 非数抛 DslError。"""
    n = _to_float(args.get("n"))
    if n is None:
        raise DslError("length_lte 缺少合法 n 参数")
    return 5.0 if len(_as_text(actual)) <= n else 1.0


def fn_non_empty(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """actual 去空白后非空返 5，否则 1。"""
    return 5.0 if _as_text(actual).strip() else 1.0


def fn_json_has_key(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """actual 可解析为 JSON 对象且含 args['key'] 返 5，否则 1；key 缺失抛 DslError。"""
    key = args.get("key")
    if not key:
        raise DslError("json_has_key 缺少 key 参数")
    text = _as_text(actual).strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return 1.0
    return 5.0 if isinstance(data, dict) and key in data else 1.0


def fn_numeric_close(expected: Any, actual: Any, args: dict[str, str]) -> float:
    """|expected - actual| <= args['tol'] 返 5，否则 1；tol 缺失 / 两侧非数抛 DslError。"""
    tol = _to_float(args.get("tol"))
    if tol is None:
        raise DslError("numeric_close 缺少合法 tol 参数")
    ev = _to_float(_as_text(expected).strip())
    av = _to_float(_as_text(actual).strip())
    if ev is None or av is None:
        raise DslError("numeric_close 需要 expected 与 actual 均为数值")
    return 5.0 if abs(ev - av) <= tol else 1.0


DSL_FUNCTIONS: dict[str, DslFn] = {
    "exact": fn_exact,
    "contains": fn_contains,
    "regex": fn_regex,
    "length_gte": fn_length_gte,
    "length_lte": fn_length_lte,
    "non_empty": fn_non_empty,
    "json_has_key": fn_json_has_key,
    "numeric_close": fn_numeric_close,
}


def get_function(name: str) -> DslFn:
    """按名取内置评分函数；未知名抛 DslError。"""
    fn = DSL_FUNCTIONS.get(name)
    if fn is None:
        raise DslError(
            f"未知 DSL 函数: {name!r}；可选: {sorted(DSL_FUNCTIONS.keys())}"
        )
    return fn
