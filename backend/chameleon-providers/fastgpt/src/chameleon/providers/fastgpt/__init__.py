"""chameleon-provider-fastgpt: FastGPT HTTP provider"""

# 必须 import config 触发 @register 装饰器副作用
from chameleon.providers.fastgpt import config as _config  # noqa: F401
from chameleon.providers.fastgpt.config import FastGPTAgentConfig
from chameleon.providers.fastgpt.provider import FastGPTProvider

PROVIDER = FastGPTProvider()

__all__ = ["PROVIDER", "FastGPTProvider", "FastGPTAgentConfig"]
__version__ = "0.1.0"
