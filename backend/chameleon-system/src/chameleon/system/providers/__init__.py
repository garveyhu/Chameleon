"""providers 管理模块（/v1/admin/providers）"""

from chameleon.system.providers.api import router as providers_admin_router

__all__ = ["providers_admin_router"]
