"""Provider 协议（ABC）

每个 provider 子包必须：
1. 继承 Provider 并实现 stream()
2. 在 __init__.py export `PROVIDER = <YourProvider>()`

invoke() 默认实现 = 聚合 stream()；provider 如有原生非流模式可 override。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from chameleon.providers.base.types import (
    InvokeContext,
    InvokeResult,
    StreamEvent,
    StreamEventType,
    _StreamAggregator,
)


class Provider(ABC):
    """Provider 抽象基类"""

    name: str  # 子类必须设置（"local" / "dify" / "fastgpt" / ...）

    @abstractmethod
    def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """流式调用 —— 必须实现"""
        raise NotImplementedError

    async def invoke(self, ctx: InvokeContext) -> InvokeResult:
        """非流式：默认聚合 stream() 实现；有原生非流模式的 provider 可 override

        中途遇到 error event → raise BusinessError（由全局 handler 兜）
        """
        from chameleon.core.api.exceptions import (
            BusinessError,
            ResultCode,
        )

        agg = _StreamAggregator(session_id=ctx.session_id, request_id=ctx.request_id)
        async for ev in self.stream(ctx):
            if ev.type == StreamEventType.error:
                code = ev.data.get("code", ResultCode.ProviderInternalError)
                msg = ev.data.get("message", "provider stream error")
                raise BusinessError(code, msg)
            agg.feed(ev)
        return agg.result()

    async def healthcheck(self) -> bool:
        """启动时 / 定时 ping。warn-only，不阻塞启动。默认返 True。"""
        return True
