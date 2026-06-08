"""AI 自动编排（A4）：自然语言描述 → GraphSpec。

AI 内核（prompt + 双轮重试 + trace）在 ``aikit.tasks.graph.generate_graph_spec``；
图结构校验依赖 ``engine.graph``，以回调注入（aikit 是底层包不能反向依赖 engine）。
"""

from __future__ import annotations

from typing import Any

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.engine.graph import GraphSpec
from chameleon.engine.graph.engine import Orchestrator


async def generate_graph_spec(description: str) -> dict[str, Any]:
    """NL 描述 → 校验通过的 GraphSpec dict（图校验注入 aikit 任务）。"""
    from chameleon.aikit.tasks.graph import GraphSpecError
    from chameleon.aikit.tasks.graph import generate_graph_spec as _generate

    def _validate(spec_dict: dict[str, Any]) -> None:
        gs = GraphSpec.model_validate(spec_dict)
        Orchestrator(gs)  # 实例化节点 → data 校验；非法 raise

    try:
        return await _generate(description, validate=_validate)
    except GraphSpecError as e:
        raise BusinessError(
            ResultCode.InternalError,
            message=f"AI 编排生成失败（校验不过）：{e}",
        ) from e
