"""媒体生成计费桥（IoC）—— 让 agentkit ctx.media 的成本归集进 trace/rollup。

媒体按张/按秒计费（`system.pricing.calc_media_cost`），定价在 system 层，而 agentkit
runner（providers-local）不依赖 system。仿 a2a_bridge / retrieval_bridge 的反转：app
启动由 system 侧注入算价 fn，runner 经 `get_media_cost_fn()` 拿成本写进 generation
观测（cost_usd），rollup 据此把媒体成本计入根行——兑现「自动计费」楔子。

fn 契约（纯参数 + float 返回，避免本层 import system）：
    async def fn(model_code: str, kind: str, params: dict) -> float | None
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

MediaCostFn = Callable[..., Awaitable[float | None]]

_FN: MediaCostFn | None = None


def set_media_cost_fn(fn: MediaCostFn) -> None:
    global _FN
    _FN = fn


def get_media_cost_fn() -> MediaCostFn | None:
    return _FN
