"""调用来源渠道（call_logs.channel）取值登记表。

入口处给 `TraceContext.channel` 盖章；会话账本 / 可观测域按渠道筛选溯源。
`call_logs.channel` 是 `String(16)` 自由文本，无 DB 枚举约束——这里集中登记取值
避免散落字符串字面量。NULL = 未标注（如图内部子观测）。
"""

from __future__ import annotations

from enum import StrEnum


class Channel(StrEnum):
    """调用来源渠道枚举。值与 call_logs.channel 落库字符串一致。"""

    API = "api"
    OPENAI = "openai"
    EMBED = "embed"
    PLAYGROUND = "playground"
    INTERNAL = "internal"
    EVAL = "eval"  # 评测跑分（dataset_run）期间的 LLM 流量
