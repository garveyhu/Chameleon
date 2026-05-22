"""GraphExecutor —— DAG 拓扑驱动的串行执行器（P18.1 MVP 版）

执行模型：
1. 加载 GraphSpec → 构 node 实例字典（node_id → Node instance）
2. 拓扑排序检测环（有环直接 raise）
3. 从 start 节点开始：BFS 推进；每节点 await execute()
4. 每节点产 NodeRunResult；选出边后把 output 传给下一节点
5. 走到 end 节点收集 output 作为 graph 最终输出

约束（P18.1 范围）：
- 串行执行（多路径分叉先 sequential 跑）；并发 fanout 留 PR #19
- 单 input 单 output（每节点只接受一个 incoming 数据流）；merge 节点留 P19
- 环 / 自环检测在 spec 校验阶段就报，运行时不再容错
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger
from pydantic import BaseModel, Field

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node, NodeStatus
from chameleon.core.graph.types import GraphSpec, NodeSpec


# 注册表：node_type → Node 子类。引用方启动时 register()，避免循环 import
_NODE_REGISTRY: dict[str, type[Node]] = {}


def register_node_type(cls: type[Node]) -> type[Node]:
    """装饰器 / 函数：把 Node 子类注册到全局 registry

    用法（在 nodes/foo.py 末尾）：
        register_node_type(FooNode)
    """
    if cls.type in _NODE_REGISTRY and _NODE_REGISTRY[cls.type] is not cls:
        raise ValueError(
            f"node_type={cls.type!r} 已注册为 {_NODE_REGISTRY[cls.type].__name__}，"
            f"不能再注册 {cls.__name__}"
        )
    _NODE_REGISTRY[cls.type] = cls
    return cls


def get_registered_node_types() -> list[str]:
    return sorted(_NODE_REGISTRY.keys())


# ── 执行结果 ─────────────────────────────────────────────


class NodeRunResult(BaseModel):
    """单节点执行结果"""

    node_id: str
    node_type: str
    status: NodeStatus
    input: Any = None
    output: Any = None
    error: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int


class RunResult(BaseModel):
    """整张图的执行结果"""

    status: NodeStatus  # success / failed
    input: Any
    output: Any = None
    error: dict[str, Any] | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    node_runs: list[NodeRunResult] = Field(default_factory=list)


# ── 拓扑 / 环检测 ─────────────────────────────────────────


def _topological_sort(spec: GraphSpec) -> list[str]:
    """Kahn 拓扑排序；有环则 raise ValueError

    返回 node_id 拓扑顺序列表。
    """
    in_degree: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)
    for n in spec.nodes:
        in_degree[n.id] = in_degree.get(n.id, 0)
    for e in spec.edges:
        adj[e.source].append(e.target)
        in_degree[e.target] += 1

    queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
    order: list[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(spec.nodes):
        unreachable = set(n.id for n in spec.nodes) - set(order)
        raise ValueError(f"图含环 / 不可达节点：{sorted(unreachable)}")
    return order


def assert_acyclic(spec: GraphSpec) -> None:
    """显式调用：spec 是否无环"""
    _topological_sort(spec)


# ── Executor ─────────────────────────────────────────────


class GraphExecutor:
    """图执行器

    用法：
        executor = GraphExecutor(spec)
        result = await executor.run(input={"query": "hi"}, ctx=ctx)
    """

    def __init__(
        self,
        spec: GraphSpec,
        *,
        node_factory: Callable[[NodeSpec], Node] | None = None,
    ) -> None:
        """
        Args:
            spec: 已校验过的 GraphSpec
            node_factory: 测试用注入；默认走全局 _NODE_REGISTRY
        """
        self.spec = spec
        self._factory = node_factory or _default_factory
        # 启动前校验：拓扑无环（spec validator 已保证 start/end 存在）
        assert_acyclic(spec)
        # 实例化所有节点（spec.data 在 Node.__init__ 里调 validate_data）
        self._nodes: dict[str, Node] = {
            n.id: self._factory(n) for n in spec.nodes
        }

    async def run(self, *, input: Any, ctx: NodeContext) -> RunResult:
        """跑整张图

        失败传播：任一节点 raise → 当前节点标 failed → graph 标 failed 提前退出。
        """
        started_at = datetime.now(timezone.utc)
        node_runs: list[NodeRunResult] = []
        current_id: str | None = self.spec.start_node().id
        cur_input: Any = input
        last_output: Any = None

        while current_id is not None:
            node = self._nodes[current_id]
            node_started = datetime.now(timezone.utc)
            try:
                output = await node.execute(ctx, cur_input)
                node_finished = datetime.now(timezone.utc)
                node_runs.append(
                    NodeRunResult(
                        node_id=node.id,
                        node_type=node.type,
                        status=NodeStatus.SUCCESS,
                        input=cur_input,
                        output=output,
                        started_at=node_started,
                        finished_at=node_finished,
                        duration_ms=_ms(node_started, node_finished),
                    )
                )
                last_output = output

                # 到 end 节点收尾
                if node.type == "end":
                    current_id = None
                    break

                # 选下一节点（含 if_else 分支）
                next_id = self._pick_next(node, output)
                if next_id is None:
                    # 没有出边但又不是 end → 半截图，算 fail
                    raise RuntimeError(
                        f"node {node.id} 无 outgoing edge 且非 end，图断裂"
                    )
                cur_input = output
                current_id = next_id
            except Exception as exc:  # noqa: BLE001
                node_finished = datetime.now(timezone.utc)
                err = {"type": type(exc).__name__, "message": str(exc)[:500]}
                node_runs.append(
                    NodeRunResult(
                        node_id=node.id,
                        node_type=node.type,
                        status=NodeStatus.FAILED,
                        input=cur_input,
                        output=None,
                        error=err,
                        started_at=node_started,
                        finished_at=node_finished,
                        duration_ms=_ms(node_started, node_finished),
                    )
                )
                logger.exception(
                    "graph node failed | run={} | node={}",
                    ctx.graph_run_id,
                    node.id,
                )
                finished_at = datetime.now(timezone.utc)
                return RunResult(
                    status=NodeStatus.FAILED,
                    input=input,
                    output=None,
                    error=err,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=_ms(started_at, finished_at),
                    node_runs=node_runs,
                )

        finished_at = datetime.now(timezone.utc)
        return RunResult(
            status=NodeStatus.SUCCESS,
            input=input,
            output=last_output,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=_ms(started_at, finished_at),
            node_runs=node_runs,
        )

    def _pick_next(self, node: Node, output: Any) -> str | None:
        """决定下一节点 id；规则：

        - if_else：调 selected_branch(output) 取 'true' / 'false'，匹配 edge.source_handle
        - 其它单出边节点：取唯一 outgoing edge
        - 多出边（非 if_else）：取第一条；fanout 留 PR #19
        """
        edges = self.spec.outgoing_edges(node.id)
        if not edges:
            return None

        if node.type == "if_else":
            branch = node.selected_branch(output)
            for e in edges:
                if e.source_handle == branch:
                    return e.target
            raise RuntimeError(
                f"if_else 节点 {node.id} 选了 branch={branch!r}，"
                f"但未找到对应 source_handle 边"
            )

        # 单出 / 多出 → 取第一条（多出走顺序 P19 改并发）
        return edges[0].target


def _default_factory(spec: NodeSpec) -> Node:
    cls = _NODE_REGISTRY.get(spec.type)
    if cls is None:
        raise ValueError(
            f"未知 node type={spec.type!r}；已注册类型：{get_registered_node_types()}"
        )
    return cls(spec)


def _ms(t0: datetime, t1: datetime) -> int:
    return int((t1 - t0).total_seconds() * 1000)


# ── 内置 node 注册 ──────────────────────────────────────


# 这里 import 一次内置节点并注册；其它 PR 加新节点时同样调 register_node_type
from chameleon.core.graph.node_base import EndNode, NoopNode, StartNode  # noqa: E402

register_node_type(NoopNode)
register_node_type(StartNode)
register_node_type(EndNode)
