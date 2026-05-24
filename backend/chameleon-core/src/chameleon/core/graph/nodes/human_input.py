"""HumanInLoopNode —— 人工回填断点（v1.1 PR A6）

工作流跑到这个节点时暂停，等待人工提交输入后从断点恢复继续跑。

机制（与 Orchestrator 协同）：
- execute() **总是**抛 HumanInputRequired —— 它只在「尚无人工输入」时被调用。
- 人工回填后 resume：Orchestrator 用 seed_outputs 把本节点的值直接重放
  （不再调 execute），下游照常推进。即「有值 → 重放跳过；无值 → 抛出暂停」。

data 配置：
    {
      "prompt": "请审核并补充",        # 可选：给审核人看的提示
      "schema": { ... },               # 可选：期望输入的 JSON schema（前端渲染表单）
      "timeout_seconds": 86400,        # 可选：超时秒数（service 层 APScheduler 据此标超时）
    }

暂停后 service 层落 human_input_pending 行 + graph_run.status=paused；
回填走 resume 接口，Orchestrator 以 seed_outputs 恢复。
"""

from __future__ import annotations

from typing import Any

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import HumanInputRequired, Node
from chameleon.core.graph.registry import register_node_type

#: timeout_seconds 硬上限（30 天）
MAX_TIMEOUT_SECONDS = 30 * 24 * 3600


class HumanInLoopNode(Node[Any, Any]):
    """人工回填断点节点"""

    type = "human_input"

    def validate_data(self, data: dict[str, Any]) -> None:
        if data.get("prompt") is not None and not isinstance(data["prompt"], str):
            raise ValueError("HumanInLoopNode.data.prompt 必须是字符串")
        if data.get("schema") is not None and not isinstance(data["schema"], dict):
            raise ValueError("HumanInLoopNode.data.schema 必须是 dict")
        ts = data.get("timeout_seconds")
        if ts is not None and (
            not isinstance(ts, int) or not 1 <= ts <= MAX_TIMEOUT_SECONDS
        ):
            raise ValueError(
                f"HumanInLoopNode.data.timeout_seconds 必须 [1, {MAX_TIMEOUT_SECONDS}]"
            )

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        # 总是抛暂停信号；有人工值时 Orchestrator 会用 seed 重放、不会走到这里。
        raise HumanInputRequired(
            self.id,
            prompt=self.spec.data.get("prompt"),
            schema=self.spec.data.get("schema"),
            node_input=input,
        )


register_node_type(HumanInLoopNode)
