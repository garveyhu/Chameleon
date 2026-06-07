"""agentkit 本地开发 dev 端点（/v1/dev/*）—— 仅开发态（CHAMELEON_DEV_TOKEN）放行。"""

from chameleon.api.dev.api import router as dev_router

__all__ = ["dev_router"]
