"""Provider 错误家族 —— 从 chameleon-core 再 export，方便 provider 作者 import"""

from chameleon.core.exceptions import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderInputError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)

__all__ = [
    "ProviderAuthError",
    "ProviderConfigError",
    "ProviderError",
    "ProviderInputError",
    "ProviderInternalError",
    "ProviderRateLimitError",
    "ProviderUnreachableError",
]
