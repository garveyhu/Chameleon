"""错误分类 —— 决定 failover 是否换 channel 重试

哲学：
- 5xx / 429 / 连接错误 / 超时 → 切下一个 channel 可能解决 → 重试
- 4xx 客户端错误（input 不合法 / 鉴权之外）→ 换 channel 也无济于事 → 不重试
- 401/403 鉴权失败 → 当前 channel 凭证有问题，换下一个可能解决 → 重试
- 业务异常（ValidationError, AgentNotFound 等）→ 不是 channel 问题 → 不重试

返 True 表示"应当尝试切下一个 channel"。
"""

from __future__ import annotations

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.providers.base.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInternalError,
    ProviderRateLimitError,
    ProviderUnreachableError,
)

# 即使是 BusinessError，下列业务码也可能是 channel 端问题 → 重试
_RETRYABLE_BUSINESS_CODES = {
    int(ResultCode.ProviderInternalError),
    int(ResultCode.ProviderAuthFailed),
}


def should_retry(exc: Exception) -> bool:
    """是否应该 failover 到下一个 channel"""
    # 1. Provider 抛的可重试异常
    if isinstance(exc, ProviderRateLimitError):
        return True
    if isinstance(exc, ProviderUnreachableError):
        return True
    if isinstance(exc, ProviderInternalError):
        return True
    if isinstance(exc, ProviderAuthError):
        # 当前 channel 的 key 失效，换一个可能有用
        return True

    # 2. ValidationError 永不重试（用户输入问题）
    if isinstance(exc, ValidationError):
        return False

    # 3. BusinessError 按业务码白名单
    if isinstance(exc, BusinessError):
        try:
            code = int(exc.code)
        except (TypeError, ValueError):
            return False
        return code in _RETRYABLE_BUSINESS_CODES

    # 4. ProviderError 基类 —— 已经在上面具体子类覆盖，到这里说明是自定义子类，
    #    保守按"假定底层是 HTTP/网络" 处理
    if isinstance(exc, ProviderError):
        return True

    # 5. 其他未知异常 —— 不重试，避免无脑放大问题
    return False
