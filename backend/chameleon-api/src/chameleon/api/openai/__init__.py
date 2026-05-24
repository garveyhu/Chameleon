"""OpenAI 兼容网关模块（/v1/chat/completions）"""

from chameleon.api.openai.api import router as openai_router

__all__ = ["openai_router"]
