"""嵌入式配置管理模块（/v1/admin/embed-configs）"""

from chameleon.system.embed_configs.api import router as embed_configs_router

__all__ = ["embed_configs_router"]
