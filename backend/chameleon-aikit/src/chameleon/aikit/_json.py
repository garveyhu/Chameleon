"""从 LLM 文本输出里抠 JSON —— 多个内部 AI 任务共用。

容忍 ```json 代码块包裹、前后噪声；取第一个 ``{...}`` 对象。
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """从模型输出抠出 JSON 对象。

    Raises:
        json.JSONDecodeError: 抠出的片段不是合法 JSON
    """
    t = text.strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1)
    else:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1:
            t = t[start : end + 1]
    return json.loads(t)
