"""Observation 嵌套上下文

Pattern：把"父调用"放进 contextvar，业务侧用 `with observe(...) as o:`
开启子观测；不传 parent_id 时自动用 contextvar 里的值。

用法：
    from chameleon.core.observe import observe, current_observation_id

    async with observe(observation_type="agent", request_id="r1") as o:
        # 这里 current_observation_id() == r1
        async with observe(observation_type="generation") as gen:
            # 自动 parent_id = r1
            ...
        async with observe(observation_type="retriever") as rt:
            # 自动 parent_id = r1
            ...

具体如何把 observation 落到 call_logs 表上由调用方（agent service）决定 ——
本模块只提供"嵌套上下文 + parent_id 自动传递"基础设施。
"""

from chameleon.core.observe.aggregator import (
    ObservationRollup,
    aggregate_rollups,
)
from chameleon.core.observe.billing import (
    PreConsumeAction,
    PreConsumeResult,
    estimate_request_tokens,
    estimate_text_tokens,
    post_consume,
    pre_consume,
    release_reservation,
)
from chameleon.core.observe.context import (
    ObservationContext,
    ObservationType,
    current_observation_id,
    observe,
)

__all__ = [
    "ObservationContext",
    "ObservationRollup",
    "ObservationType",
    "PreConsumeAction",
    "PreConsumeResult",
    "aggregate_rollups",
    "current_observation_id",
    "estimate_request_tokens",
    "estimate_text_tokens",
    "observe",
    "post_consume",
    "pre_consume",
    "release_reservation",
]
