"""Workspace admin module —— P19.3 PR #38

/v1/admin/workspaces 接口：workspace CRUD + members CRUD
"""

from chameleon.system.workspaces.api import router as workspaces_router

__all__ = ["workspaces_router"]
