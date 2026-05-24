"""节点类型注册表

新 Node 子类用 register_node_type 装饰器加进来；Orchestrator 通过 _default_factory
按 NodeSpec.type 查 class 实例化。

红线：
- 同一 type 不能重复注册不同 class（启动期失败比运行时神秘 bug 好）
- 注册表全局唯一（多 Orchestrator 实例共享）
"""

from __future__ import annotations

from chameleon.core.graph.node_base import EndNode, Node, NoopNode, StartNode
from chameleon.core.graph.types import NodeSpec


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


def default_factory(spec: NodeSpec) -> Node:
    """按 spec.type 实例化 Node；未知 type raise"""
    cls = _NODE_REGISTRY.get(spec.type)
    if cls is None:
        raise ValueError(
            f"未知 node type={spec.type!r}；已注册类型：{get_registered_node_types()}"
        )
    return cls(spec)


# ── 内置节点注册（start / end / noop）────────────────────────
# 业务节点（llm / kb / tool / if_else / agent_debate）在各自模块末尾调
# register_node_type 加进来；不集中在这里防 import 循环。
register_node_type(NoopNode)
register_node_type(StartNode)
register_node_type(EndNode)
