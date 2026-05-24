"""子图执行辅助 —— IterationNode / ParallelNode 共用（v1.1 PR A5）

两类节点都"对某个 input 跑一张完整子图（body GraphSpec）"，差异只在调度方式
（iteration = 同 body 逐 item；parallel = 多 branch 并发）。把"派生子上下文 +
嵌套 Orchestrator 跑 body + 深度守卫"抽到这里，避免逻辑分叉。
"""

from __future__ import annotations

from typing import Any

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.results import RunResult

#: 子图嵌套最大深度（防 body 里再套 iteration/parallel 无限递归爆栈）
MAX_NEST_DEPTH = 8


def ensure_nest_depth(ctx: NodeContext, node_label: str) -> None:
    """超过最大嵌套深度直接拒绝（在节点 execute 入口调）"""
    if ctx.depth >= MAX_NEST_DEPTH:
        raise ValueError(
            f"{node_label} 嵌套过深（depth={ctx.depth} ≥ {MAX_NEST_DEPTH}）"
        )


async def run_subgraph(
    ctx: NodeContext,
    body_spec: Any,
    sub_input: Any,
    *,
    request_suffix: str,
) -> RunResult:
    """用嵌套 Orchestrator 跑一张 body 子图

    派生子上下文：depth+1（配合 ensure_nest_depth 防递归）、request_id 追加
    suffix（trace 里区分父节点与各子运行）。返回子图 RunResult，由调用方按
    自己的语义（map 收集 / fork-join）处理 status / output。
    """
    from chameleon.core.graph.engine import Orchestrator

    sub_ctx = ctx.model_copy(
        update={
            "depth": ctx.depth + 1,
            "request_id": f"{ctx.request_id}.{request_suffix}",
        }
    )
    return await Orchestrator(body_spec).run(input=sub_input, ctx=sub_ctx)
