"""dashboard 模块（/v1/admin/dashboard）

综合统计：QPS / 调用量 / 错误率 / token 消耗 / top agents / top apps
全部基于 call_logs 表实时聚合，dashboard 接口性能在 v0.2 范围内可接受。
"""

from chameleon.system.dashboard.api import router as dashboard_router

__all__ = ["dashboard_router"]
