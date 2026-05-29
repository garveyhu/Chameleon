"""节点执行时的只读运行时上下文

红线（见 docs/plans/2026-05-23-p18-detail.md §2）：
GraphEngine Node 之间不共享可变状态。本类只承载只读元数据，
节点之间的数据流必须通过 edges 显式声明（input/output 走 executor 的传递参数）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeContext(BaseModel):
    """节点 execute() 入参的只读上下文

    业务关键字段：
    - request_id：本次 graph_run 的根 trace id（写入 call_logs.parent_id 上链）
    - graph_id / graph_run_id：写入 graph_node_runs 时的关联
    - depth：当前节点在 DAG 中的拓扑层级（用于诊断 / 防递归保护）
    - started_at：run 起始时间
    - extra：业务自定义（如 user_id / locale），节点只读

    """

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(min_length=1, max_length=64)
    graph_id: int
    graph_run_id: int
    depth: int = Field(default=0, ge=0, le=64)
    started_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)

    def child(self, *, depth_inc: int = 1) -> "NodeContext":
        """fork 一份子上下文（depth+1）—— 给嵌套场景（虽然 P18.1 暂不递归）"""
        return self.model_copy(update={"depth": self.depth + depth_inc})
