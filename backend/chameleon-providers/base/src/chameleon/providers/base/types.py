"""Provider 抽象层核心数据类型 —— 已迁移至 chameleon.core.runtime_types（纯协议层）。

这些是共享运行时协议类型（AgentDef/InvokeContext/StreamEvent/InvokeResult 等），本就属
"纯协议" core 层。迁到 core 后 agentkit 公共 SDK 只依赖精简 core（不再经 providers-base
拉 data 重依赖链）。本模块 re-export 保持 `chameleon.providers.base.types` 稳定导入路径。
"""

from __future__ import annotations

from chameleon.core.runtime_types import *  # noqa: F403  re-export（含 __all__ 下划线名）
