"""chameleon-providers-base: Provider 协议 + AgentDef + StreamEvent + registry

任何 Provider 实现都依赖本包。任何业务模块都通过 PROVIDERS / AGENTS 全局 dict 访问。
"""

from chameleon.providers.base.errors import (
    ProviderAuthError,
    ProviderConfigError,
    ProviderError,
    ProviderInputError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.registry import (
    AGENTS,
    PROVIDERS,
    build_agent_registry,
    build_provider_registry,
    init_registry,
    reset_registry_for_test,
)
from chameleon.providers.base.types import (
    AgentDef,
    Citation,
    InvokeContext,
    InvokeResult,
    Message,
    StepRecord,
    StreamEvent,
    StreamEventType,
    ToolCallRecord,
    Usage,
)

__all__ = [
    "AGENTS",
    "AgentDef",
    "Citation",
    "InvokeContext",
    "InvokeResult",
    "Message",
    "PROVIDERS",
    "Provider",
    "ProviderAuthError",
    "ProviderConfigError",
    "ProviderError",
    "ProviderInputError",
    "ProviderInternalError",
    "ProviderRateLimitError",
    "ProviderUnreachableError",
    "StepRecord",
    "StreamEvent",
    "StreamEventType",
    "ToolCallRecord",
    "Usage",
    "build_agent_registry",
    "build_provider_registry",
    "init_registry",
    "reset_registry_for_test",
]

__version__ = "0.1.0"
