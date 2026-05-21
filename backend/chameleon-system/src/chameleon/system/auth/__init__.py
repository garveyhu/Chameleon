"""管理面板鉴权 + RBAC 模块

挂点：/v1/auth/*（无 admin scope 校验，部分接口需登录）

公开 API：
- service.login / refresh / logout / change_password
- dependencies.get_current_user / require_role / require_permission
- api.router  ── FastAPI router
"""

from chameleon.system.auth.api import router as auth_router

__all__ = ["auth_router"]
