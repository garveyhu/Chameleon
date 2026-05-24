"""路由层 —— Channel + Ability 矩阵的解析引擎

公开 API：
- resolve_channel(session, model_code, ...) —— 按 model_code 路由到 channel
- mark_success / mark_failed —— P17.A2 健康监控写入点

业务侧 invoke 前调 resolve_channel；调用结束按结果调 mark_*。
"""

from chameleon.core.routing.error_classify import should_retry
from chameleon.core.routing.failover import (
    build_channel_override,
    invoke_with_failover,
)
from chameleon.core.routing.key_pool import (
    quarantine_key,
    select_channel_key,
)
from chameleon.core.routing.router import (
    NoSatisfiedChannelError,
    mark_failed,
    mark_success,
    resolve_channel,
)

__all__ = [
    "resolve_channel",
    "mark_success",
    "mark_failed",
    "NoSatisfiedChannelError",
    "should_retry",
    "invoke_with_failover",
    "build_channel_override",
    "quarantine_key",
    "select_channel_key",
]
