"""tools 管理模块（/v1/admin/tools）

业务：内置 Tool 类在 chameleon.core.tools.builtins/*；
本模块负责持久化 admin 配的 (tool_key, config, enabled)。
"""

from chameleon.system.tools.api import router as tools_router

__all__ = ["tools_router"]
