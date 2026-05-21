"""审计日志模块（/v1/admin/audit-logs）

记录所有 admin 写操作。供 admin 在前端查询。
中间件：write_audit_log 由 service / api 层显式调（不全局拦截，
避免错误注入伪造日志）。
"""

from chameleon.system.audit_logs.api import router as audit_logs_router
from chameleon.system.audit_logs.recorder import write_audit_log

__all__ = ["audit_logs_router", "write_audit_log"]
