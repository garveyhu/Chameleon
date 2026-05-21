"""默认 RBAC 数据定义（permission 清单 + 内置角色映射）

修改本文件 = 重新设计权限体系；下次启动空 DB 时自动生效。
对已存在 DB：不会回滚已 seed 的数据，新加 permission/role 需要 admin 在前端补。
"""

from __future__ import annotations

# ── 权限点清单 ──────────────────────────────────────────────
# 命名约定：<resource>:<action>，action ∈ {read, write, delete, manage}
# resource:* 通配同 resource 所有 action；*:* 全通配

_RESOURCES: dict[str, tuple[str, ...]] = {
    "users": ("read", "write", "delete"),
    "roles": ("read", "write", "delete"),
    "permissions": ("read",),  # permissions 表只读 / seed-only
    "apps": ("read", "write", "delete"),
    "api_keys": ("read", "write", "delete"),
    "providers": ("read", "write", "delete"),
    "models": ("read", "write", "delete"),
    "agents": ("read", "write", "delete"),
    "kbs": ("read", "write", "delete"),
    "embed_configs": ("read", "write", "delete"),
    "call_logs": ("read",),
    "audit_logs": ("read",),
    "dashboard": ("read",),
    "settings": ("read", "write"),
}


def all_permissions() -> list[tuple[str, str, str, str]]:
    """所有 (code, resource, action, description) 元组"""
    descriptions = {
        "read": "查看",
        "write": "创建 / 修改",
        "delete": "删除",
        "manage": "高级管理",
    }
    out: list[tuple[str, str, str, str]] = []
    for resource, actions in _RESOURCES.items():
        for action in actions:
            code = f"{resource}:{action}"
            desc = f"{descriptions.get(action, action)}{resource}"
            out.append((code, resource, action, desc))
    return out


# ── 内置角色 ────────────────────────────────────────────────


_ALL_PERM_CODES = [code for code, _, _, _ in all_permissions()]

# admin：全部权限（用 *:* 通配，未来加权限点不用回头改 seed）
_ADMIN_PERMS = ["*:*"]

# developer：业务资源 CRUD + 看 dashboard + call_logs，不能管 users / roles / permissions / settings
_DEVELOPER_RESOURCES = {
    "apps", "api_keys", "providers", "models", "agents",
    "kbs", "embed_configs", "call_logs", "dashboard",
}
_DEVELOPER_PERMS = sorted(
    c for c, r, _, _ in all_permissions() if r in _DEVELOPER_RESOURCES
)

# viewer：只读全部资源 + dashboard
_VIEWER_PERMS = sorted(
    c for c, _, a, _ in all_permissions() if a == "read"
)


def default_roles() -> list[tuple[str, str, str, list[str]]]:
    """返回 (code, name, description, permission_codes) 列表

    permission_codes 含 "*:*" 时由 require_permission 通配支持。
    """
    return [
        (
            "admin",
            "管理员",
            "拥有所有权限，可管理用户 / 角色 / 业务资源",
            _ADMIN_PERMS,
        ),
        (
            "developer",
            "开发者",
            "管理业务资源（agents / models / providers / apps / kbs），不能管用户和角色",
            _DEVELOPER_PERMS,
        ),
        (
            "viewer",
            "观察者",
            "只读所有资源 + dashboard，不能修改任何东西",
            _VIEWER_PERMS,
        ),
    ]


# ── 默认 admin 账号 ────────────────────────────────────────


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_DISPLAY_NAME = "系统管理员"
DEFAULT_ADMIN_LOCALE = "zh-CN"
