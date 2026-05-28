"""agent 模块：仅一个扁平入口 `flat_api_router`（POST /v1/invoke + GET /v1/info）

管理 / 列表 / 详情走 /v1/admin/agents/*（JWT 鉴权）；
对外服务调用统一靠 Bearer key + 扁平路径（key 即应用身份，Dify 套路）。
"""

from chameleon.api.agent.api import flat_router as flat_api_router

__all__ = ["flat_api_router"]
