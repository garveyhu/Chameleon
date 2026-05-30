"""观测落库实现层：generation 回调 / graph 节点 span / rollup 聚合。

- GenerationRecorder：LangChain BaseLLM 异步回调，每次模型调用落一条 generation call_log
- persist_node_spans：graph 引擎节点 span 落库
- aggregate_rollups / ObservationRollup：根行 rollup 聚合（纯函数）

ObservationSink / TraceContext 等协议与上下文在 chameleon.core.observe。
"""

from chameleon.integrations.observe.aggregator import (
    ObservationRollup,
    aggregate_rollups,
)
from chameleon.integrations.observe.graph_spans import persist_node_spans
from chameleon.integrations.observe.llm_recorder import (
    CallLogCallbackHandler,
    GenerationRecorder,
    get_calllog_handler,
)

__all__ = [
    "CallLogCallbackHandler",
    "GenerationRecorder",
    "ObservationRollup",
    "aggregate_rollups",
    "get_calllog_handler",
    "persist_node_spans",
]
