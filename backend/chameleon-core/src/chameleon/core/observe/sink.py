"""ObservationSink —— 观测落库的可注入后端（解耦 core→system）。

背景：core 的 observe 切面（llm_recorder / graph_spans）原本 lazy import
`chameleon.system.api_key.service.record_call` 落 call_logs —— 这是 core→system 的
上行依赖（record_call 在顶层 system，还含 pricing 计费）。

改法：core 只定义 sink 协议 + 注册表 + `record_observation` 入口；具体「写 call_logs」
的实现由上层 app 启动时 `set_observation_sink(...)` 注入。core 不再 import chameleon.system。

这也是组件级回调切面（方案 A）的地基：sink 是可插拔 handler，未来可注册多个
（落库 / 导出 LangSmith / 在线评测采样）。
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger


class ObservationSink(Protocol):
    """落一条 observation（= 一行 call_log）。字段与 system.record_call 对齐。

    session 用 Any 不绑 sqlalchemy（core 保持纯净）；实现方收到的是 AsyncSession。
    """

    async def __call__(self, session: Any, **fields: Any) -> None: ...


_SINK: ObservationSink | None = None
_warned = False


def set_observation_sink(sink: ObservationSink | None) -> None:
    """注册观测落库后端（上层 app 启动 / 测试 conftest 调用一次）。None 可清空。"""
    global _SINK
    _SINK = sink


def get_observation_sink() -> ObservationSink | None:
    return _SINK


async def record_observation(session: Any, **fields: Any) -> None:
    """把一条 observation 落库 —— 委托注册的 sink；未注册则告警一次后跳过。

    core 侧 observe 切面统一调它，而非直接 import system.record_call。
    """
    global _warned
    if _SINK is None:
        if not _warned:
            logger.warning(
                "observation sink 未注册，观测记录被跳过"
                "（应在 app 启动 / 测试 conftest 里 set_observation_sink）"
            )
            _warned = True
        return
    await _SINK(session, **fields)
