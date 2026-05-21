"""嵌入式业务 API（/v1/embed/*）

业务方网页通过 widget JS 或 iframe 拉本接口；不需要业务方注册 API key。
鉴权流程：embed_key 是公开标识 + Origin 白名单 + 短期 session_token。
"""

from chameleon.api.embed.api import router as embed_router

__all__ = ["embed_router"]
