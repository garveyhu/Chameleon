"""chameleon-provider-dify: DIFY HTTP provider"""

from chameleon.providers.dify.provider import DifyProvider

PROVIDER = DifyProvider()

__all__ = ["PROVIDER", "DifyProvider"]
__version__ = "0.1.0"
