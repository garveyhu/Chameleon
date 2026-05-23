"""Plugins admin module —— P19.2 PR #34

/v1/admin/plugins 接口：列表 / 详情 / install / enable / disable / reload / uninstall
"""

from chameleon.system.plugins.api import router as plugins_router

__all__ = ["plugins_router"]
