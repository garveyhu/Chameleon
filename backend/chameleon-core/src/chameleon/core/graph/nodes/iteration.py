"""IterationNode —— 对列表的每个元素跑一遍子图（map / loop，v1.1 PR A4）

一个节点搞定"对 N 个 item 各跑一段 workflow"（如"对 5 个 URL 各调 LLM 总结"）。
子图（body）是一张完整的 GraphSpec，IterationNode 对每个 item 用一个新的
Orchestrator 跑 body（真子图嵌套），把每个 item 的 body 输出收成列表。

data 配置：
    {
      "body": { GraphSpec dict },   # 必填：每个 item 跑的子图（含自己的 start/end）
      "items_path": "urls",          # 可选：从 input dict 取数组的 dot 路径；
                                      #       不填则要求 input 本身就是 list
      "item_input_key": "url",       # 可选：子图 input = {item_input_key: item}；
                                      #       不填则 item 直接作为子图 input
      "early_stop": <expr>,          # 可选：对每个 item 的 body 输出求值（if_else 表达式），
                                      #       truthy 则停止后续迭代（强制串行）
      "max_iterations": 100,         # 可选：硬上限（默认 100，cap 1000）
      "concurrency": 1,              # 可选：>1 并行跑（无 early_stop 时），保序收集
    }

output：
    {
      "items": [body_output_0, body_output_1, ...],   # 每个 item 的子图输出（保序）
      "count": N,                                       # 实际跑了几个
      "stopped_early": bool,
      "stopped_at": index | None,                       # early_stop 命中的下标
    }
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.nodes._subgraph import (
    MAX_NEST_DEPTH,
    ensure_nest_depth,
    run_subgraph,
)
from chameleon.core.graph.nodes.if_else import eval_condition, validate_condition
from chameleon.core.graph.registry import register_node_type

#: 单节点最大迭代数（防超大列表打爆）
DEFAULT_MAX_ITERATIONS = 100
MAX_ITERATIONS_CAP = 1000
#: 并行上限
MAX_ITERATION_CONCURRENCY = 20

__all__ = ["IterationNode", "MAX_NEST_DEPTH"]


class IterationNode(Node[Any, dict]):
    """对列表逐元素跑子图"""

    type = "iteration"

    def validate_data(self, data: dict[str, Any]) -> None:
        body = data.get("body")
        if not isinstance(body, dict):
            raise ValueError("IterationNode.data.body 必填（子图 GraphSpec dict）")
        # 校验 body 是合法子图 + 实例化各节点（深度校验 config）
        try:
            from chameleon.core.graph.engine import Orchestrator
            from chameleon.core.graph.types import GraphSpec

            Orchestrator(GraphSpec.model_validate(body))
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"IterationNode.data.body 非法子图: {e}") from e

        mi = data.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        if not isinstance(mi, int) or not 1 <= mi <= MAX_ITERATIONS_CAP:
            raise ValueError(
                f"IterationNode.data.max_iterations 必须 [1, {MAX_ITERATIONS_CAP}]"
            )

        c = data.get("concurrency", 1)
        if not isinstance(c, int) or not 1 <= c <= MAX_ITERATION_CONCURRENCY:
            raise ValueError(
                f"IterationNode.data.concurrency 必须 [1, {MAX_ITERATION_CONCURRENCY}]"
            )

        if data.get("early_stop") is not None:
            validate_condition(data["early_stop"])

        if data.get("items_path") is not None and not isinstance(
            data["items_path"], str
        ):
            raise ValueError("IterationNode.data.items_path 必须是字符串 dot 路径")
        if data.get("item_input_key") is not None and not isinstance(
            data["item_input_key"], str
        ):
            raise ValueError("IterationNode.data.item_input_key 必须是字符串")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        ensure_nest_depth(ctx, "IterationNode")

        from chameleon.core.graph.types import GraphSpec

        body_spec = GraphSpec.model_validate(self.spec.data["body"])
        max_iter = int(self.spec.data.get("max_iterations", DEFAULT_MAX_ITERATIONS))
        concurrency = int(self.spec.data.get("concurrency", 1))
        early_stop = self.spec.data.get("early_stop")

        items = self._resolve_items(input)[:max_iter]

        logger.info(
            "iteration {} | items={} | concurrency={} | early_stop={}",
            self.id,
            len(items),
            concurrency,
            early_stop is not None,
        )

        # early_stop 依赖顺序 → 强制串行
        if early_stop is not None or concurrency == 1:
            return await self._run_serial(ctx, items, body_spec, early_stop)
        return await self._run_parallel(ctx, items, body_spec, concurrency)

    # ── 串行（支持 early_stop）─────────────────────────────

    async def _run_serial(
        self,
        ctx: NodeContext,
        items: list,
        body_spec: Any,
        early_stop: Any,
    ) -> dict:
        outputs: list[Any] = []
        stopped_at: int | None = None
        for idx, item in enumerate(items):
            out = await self._run_one(ctx, idx, item, body_spec)
            outputs.append(out)
            if early_stop is not None and eval_condition(early_stop, out):
                stopped_at = idx
                break
        return {
            "items": outputs,
            "count": len(outputs),
            "stopped_early": stopped_at is not None,
            "stopped_at": stopped_at,
        }

    # ── 并行（无 early_stop）保序收集 ──────────────────────

    async def _run_parallel(
        self,
        ctx: NodeContext,
        items: list,
        body_spec: Any,
        concurrency: int,
    ) -> dict:
        import asyncio

        sem = asyncio.Semaphore(concurrency)

        async def _guarded(idx: int, item: Any) -> Any:
            async with sem:
                return await self._run_one(ctx, idx, item, body_spec)

        outputs = await asyncio.gather(
            *(_guarded(i, it) for i, it in enumerate(items))
        )
        return {
            "items": list(outputs),
            "count": len(outputs),
            "stopped_early": False,
            "stopped_at": None,
        }

    # ── 单个 item 跑子图 ──────────────────────────────────

    async def _run_one(
        self, ctx: NodeContext, idx: int, item: Any, body_spec: Any
    ) -> Any:
        item_key = self.spec.data.get("item_input_key")
        sub_input = {item_key: item} if item_key else item
        result = await run_subgraph(
            ctx, body_spec, sub_input, request_suffix=f"iter.{idx}"
        )
        if result.status.value != "success":
            err = result.error or {}
            raise RuntimeError(
                f"iteration item[{idx}] 子图失败: "
                f"{err.get('type')}: {err.get('message')}"
            )
        return result.output

    # ── helpers ───────────────────────────────────────────

    def _resolve_items(self, input: Any) -> list:
        path = self.spec.data.get("items_path")
        src: Any = input
        if path and isinstance(input, dict):
            src = _get_by_path(input, path)
        if not isinstance(src, list):
            raise ValueError(
                f"IterationNode 需要 list 输入（items_path={path!r}），"
                f"实得 {type(src).__name__}"
            )
        return src


def _get_by_path(data: dict, path: str) -> Any:
    """dot 路径取值：'a.b' → data['a']['b']，缺失返 None"""
    cur: Any = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


register_node_type(IterationNode)
