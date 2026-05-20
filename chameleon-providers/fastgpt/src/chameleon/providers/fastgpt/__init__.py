"""chameleon-provider-fastgpt: FastGPT HTTP provider"""

from chameleon.providers.fastgpt.provider import FastGPTProvider

PROVIDER = FastGPTProvider()

__all__ = ["PROVIDER", "FastGPTProvider"]
__version__ = "0.1.0"
