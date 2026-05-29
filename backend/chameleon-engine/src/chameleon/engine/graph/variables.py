"""工作流变量引用解析（参考 Dify VariablePool 的 {{#path#}} 语法）

让任意节点的文本配置（如 LLM system_prompt / prompt_template）引用：
- 系统变量：{{#sys.query#}} / {{#sys.history#}} / {{#sys.conversation_id#}}
- 上游节点输出：{{#<node_id>.<field>#}}（支持点路径 / 列表下标）

解析时从一份「变量快照」dict 取值：{"sys": {...}, "<node_id>": <output>, ...}。
取不到的引用替换为空串（与 Dify 一致：缺失即空，不报错）。
"""

from __future__ import annotations

import json
import re
from typing import Any

#: {{#a.b.c#}} —— path 为点分段（字母数字下划线）
_REF_RE = re.compile(r"\{\{#\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\s*#\}\}")


def _lookup(path: str, variables: dict[str, Any]) -> Any:
    """按点路径在快照里取值；list 段按整数下标。取不到返回 None。"""
    cur: Any = variables
    for seg in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def _render(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def resolve_in_text(text: str, variables: dict[str, Any]) -> str:
    """把 text 里所有 {{#path#}} 引用替换为快照中的值（字符串插值）。"""
    if not text or "{{#" not in text:
        return text

    def _sub(m: re.Match[str]) -> str:
        return _render(_lookup(m.group(1), variables))

    return _REF_RE.sub(_sub, text)
