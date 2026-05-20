"""admin 模块：调用审计 + provider 健康状态查询

api_key 管理 / 撤销 在 modules/api_key/。本模块专注 call_logs + providers/status。
"""

from chameleon.app.modules.admin.api import router as admin_router

__all__ = ["admin_router"]
