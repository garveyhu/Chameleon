"""Observation 双 ContextVar 上下文

两层结构：
- **TraceContext**（请求级）：入口处 `open_trace_scope(...)` 一次性写入，整段
  请求生命周期内不变。承载 request_id / app_id / api_key_id / channel /
  agent_key / session_id / end_user_id —— 用于 BaseLLM 回调里写 call_log
  generation 行时的归属冗余。
- **ObservationContext**（per-span 嵌套）：业务侧 `async with observe(...) as o:`
  开启子观测；不传 parent_id 时自动用 contextvar 里的当前值。

S7 起，generation 类型的观测**不应**由调用方手开（BaseLLM 回调自动落）；
调用方只开 type="span"（timing 段）或 type="agent"/"tool"/"retriever" 等其他类型。

用法：
    from chameleon.core.observe import open_trace_scope, observe, TraceContext

    async with open_trace_scope(TraceContext(request_id="r1", channel="api", ...)):
        async with observe(observation_type="agent", request_id="r1") as o:
            async with observe(observation_type="retriever") as rt:
                # 自动 parent_id = r1
                ...
            # 这里调任意 LLM 都会自动落一条 generation call_log（parent_id 链接）

具体如何把 observation 落到 call_logs 表上：generation 由 BaseLLM 回调自动；
其他类型由业务层显式 record_call。
"""

from chameleon.core.observe.aggregator import (
    ObservationRollup,
    aggregate_rollups,
)
from chameleon.core.observe.context import (
    ObservationContext,
    ObservationType,
    TraceContext,
    current_observation_id,
    current_trace_context,
    observe,
    open_trace_scope,
    reset_trace_context,
    set_trace_context,
)
from chameleon.core.observe.sink import (
    ObservationSink,
    get_observation_sink,
    record_observation,
    set_observation_sink,
)

__all__ = [
    "ObservationContext",
    "ObservationRollup",
    "ObservationSink",
    "ObservationType",
    "TraceContext",
    "aggregate_rollups",
    "current_observation_id",
    "current_trace_context",
    "get_observation_sink",
    "observe",
    "open_trace_scope",
    "record_observation",
    "reset_trace_context",
    "set_observation_sink",
    "set_trace_context",
]
