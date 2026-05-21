"""apps 管理模块（/v1/admin/apps）

业务应用 CRUD + 应用关联 agent 授权 + 应用下子表 api_keys 子列表。
"""

from chameleon.system.apps.api import router as apps_router

__all__ = ["apps_router"]
