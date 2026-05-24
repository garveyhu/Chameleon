"""Node 抽象基类（泛型 input/output 类型）

Node 实现注意事项：
- 不持有可变全局状态（红线）
- execute() 必须 async；同步阻塞操作放 to_thread / executor
- 异常直接 raise；executor 负责捕获 + 写 graph_node_runs.error
- 输出必须 JSON-serializable（要落 graph_node_runs.output JSONB）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, Generic, TypeVar

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.types import NodeSpec

#: 流式节点把文本片段推给上游的回调（Orchestrator 注入；非流式场景为 None）。
#: 红线：execute() 签名不动 —— 流式走独立可选入口 execute_stream()。
DeltaSink = Callable[[str], Awaitable[None]]


class NodeStatus(StrEnum):
    """单节点执行状态"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # if_else 未选中的分支
    PAUSED = "paused"  # human_input 节点等待人工回填（A6）


class HumanInputRequired(Exception):
    """HumanInLoopNode 触发的暂停信号（A6）

    节点 execute 抛出 → Orchestrator 不当失败处理，而是把整图置 PAUSED，
    快照已完成节点输出供 resume 时 seed 重放；持久化与回填由 service 层负责。
    """

    def __init__(
        self,
        node_id: str,
        *,
        prompt: str | None = None,
        schema: dict[str, Any] | None = None,
        node_input: Any = None,
    ) -> None:
        self.node_id = node_id
        self.prompt = prompt
        self.schema = schema
        self.node_input = node_input
        super().__init__(f"human input required at node {node_id!r}")


NodeInputT = TypeVar("NodeInputT")
NodeOutputT = TypeVar("NodeOutputT")


class Node(ABC, Generic[NodeInputT, NodeOutputT]):
    """节点抽象基类

    子类必须：
    1. 在 __init__ 接收 NodeSpec，调 super().__init__(spec) 保留它
    2. 实现 async def execute(ctx, input) -> output

    可选：
    - validate_data(spec.data) 在 spec 加载时被 executor 调用做 config 校验
    - selected_branch(output) 仅 if_else 节点需要：决定走哪条 source_handle
    """

    #: 子类必须覆盖；与 NodeType literal 一致
    type: str = "abstract"

    def __init__(self, spec: NodeSpec) -> None:
        if spec.type != self.type:
            raise TypeError(
                f"NodeSpec.type={spec.type!r} 与 Node.type={self.type!r} 不匹配"
            )
        self.spec = spec
        self.id = spec.id
        self.name = spec.name or spec.id
        self.validate_data(spec.data)

    def validate_data(self, data: dict[str, Any]) -> None:
        """子类可覆盖：校验 spec.data；默认不做事"""
        return None

    @abstractmethod
    async def execute(
        self, ctx: NodeContext, input: NodeInputT
    ) -> NodeOutputT:
        """节点核心逻辑

        异常会被 executor 捕获 + 转 NodeRunResult(error=...)。
        正常返回的值会序列化到 graph_node_runs.output。
        """
        raise NotImplementedError

    async def execute_stream(
        self,
        ctx: NodeContext,
        input: NodeInputT,
        emit: DeltaSink | None,
    ) -> NodeOutputT:
        """流式入口（可选）—— Orchestrator 在 SSE 模式下调用

        默认实现 = 非流式：直接 execute()，忽略 emit。流式节点（如 LLMNode）
        覆盖此方法，边产 token 边 await emit(text)，最后返回与 execute() 同形的
        完整 output（仍要落 graph_node_runs.output）。

        emit 为 None 时（batch 模式）等价 execute()。
        """
        return await self.execute(ctx, input)

    def selected_branch(self, output: NodeOutputT) -> str | None:
        """if_else 节点决定走哪个 source_handle（'true' / 'false'）

        默认返回 None：单出边，executor 走唯一出边。
        if_else 子类覆盖此方法返回 'true' / 'false'。
        """
        return None


class NoopNode(Node[Any, Any]):
    """占位节点 —— 仅做测试 / 跑通 executor 流"""

    type = "noop"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return {"passthrough": input, "node_id": self.id}


class StartNode(Node[Any, Any]):
    """入口节点 —— 透传 graph 的 input 到下一节点"""

    type = "start"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return input


class EndNode(Node[Any, Any]):
    """终态节点 —— 聚合输入作为 graph 输出"""

    type = "end"

    async def execute(self, ctx: NodeContext, input: Any) -> Any:
        return input
