"""scores 管理模块（/v1/admin/scores）

call_log 上的"评分 / 反馈"事件聚合。
对外暴露：
- admin CRUD（人工标注、查看）
- 不直接暴露写端点给 widget——widget 反馈走 /v1/embed/{key}/feedback
  转发到本模块的 service.create_score()
"""

from chameleon.system.scores.api import router as scores_router

__all__ = ["scores_router"]
