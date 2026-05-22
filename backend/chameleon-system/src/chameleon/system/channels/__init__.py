"""channels 管理模块（/v1/admin/channels）

每个 channel = 一个 provider 的一条上游 key + 调度元数据（priority/weight/status）。
为 P17.A1.2 abilities 矩阵 + P17.A2 failover 提供底层资源。
"""

from chameleon.system.channels.api import router as channels_router

__all__ = ["channels_router"]
