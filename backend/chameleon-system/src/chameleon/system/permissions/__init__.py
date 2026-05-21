"""permissions 只读模块（/v1/admin/permissions）

permission 表由 seed 维护，前端只能列出供 role 分配。
"""

from chameleon.system.permissions.api import router as permissions_router

__all__ = ["permissions_router"]
