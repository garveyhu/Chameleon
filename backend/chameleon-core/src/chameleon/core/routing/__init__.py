"""路由层 —— Channel + Ability 矩阵的解析引擎

公开 API：
- resolve_channel(session, model_code, ...) —— 按 model_code 路由到 channel
- mark_success / mark_failed —— P17.A2 健康监控写入点

业务侧 invoke 前调 resolve_channel；调用结束按结果调 mark_*。
"""

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
]
