"""chameleon-provider-dify: DIFY HTTP provider"""

# 必须 import config 触发 @register 装饰器副作用
from chameleon.providers.dify import config as _config  # noqa: F401
from chameleon.providers.dify.config import DifyAgentConfig
from chameleon.providers.dify.provider import DifyProvider

PROVIDER = DifyProvider()

__all__ = ["PROVIDER", "DifyProvider", "DifyAgentConfig"]
__version__ = "0.1.0"
