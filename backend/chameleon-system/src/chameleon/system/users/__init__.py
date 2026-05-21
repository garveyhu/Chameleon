"""users 管理模块（/v1/admin/users）"""

from chameleon.system.users.api import router as users_router

__all__ = ["users_router"]
