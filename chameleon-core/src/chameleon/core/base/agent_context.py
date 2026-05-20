"""AgentContext —— agent 运行时上下文（仿 sage AgentContext）

差异：sage 还含 space_id / user_id / db；chameleon v1 简化为 app_id / session_id +
任意 context_vars dict（与 InvokeContext 一致）。

agent 可选用法：从 ctx.context_vars 读业务字段（如 tenant / lang）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """智能体运行上下文（轻量版）"""

    app_id: str
    session_id: str
    request_id: str | None = None
    app_config: dict[str, Any] = field(default_factory=dict)  # agent 配置项
    context_vars: dict[str, Any] = field(default_factory=dict)  # 客户端透传业务上下文

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.app_config.get(key, default)

    def get_var(self, key: str, default: Any = None) -> Any:
        return self.context_vars.get(key, default)
