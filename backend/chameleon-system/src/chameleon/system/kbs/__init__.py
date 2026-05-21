"""knowledge bases 管理模块（/v1/admin/kbs）

业务方走 /v1/knowledge/* CRUD；admin 这里走 /v1/admin/kbs/* 查看 + 强力管理。
"""

from chameleon.system.kbs.api import router as kbs_admin_router

__all__ = ["kbs_admin_router"]
