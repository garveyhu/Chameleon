"""ParallelNode —— fork-join 并发分支（v1.1 PR A5）

把同一个 input fork 给 N 条**不同的** branch 子图并发执行，再按 join_strategy
汇合结果。与 IterationNode（同 body 逐 item）的区别：parallel 是不同 branch
同时跑（fork-join）。

data 配置：
    {
      "branches": [
        {"key": "summarize", "body": { GraphSpec dict }},
        {"key": "translate", "body": { GraphSpec dict }},
        ...                                  # 至少 2 条
      ],
      "join_strategy": "collect",            # collect | merge | race
      "concurrency": 5,                       # 可选；默认 = 分支数（全并发）
    }

input：原样 fork 给每条 branch 子图（每条 branch 拿到相同 input）。

join_strategy：
    collect（默认）：等全部分支成功 → {branches: {key: output}, branch_runs}
    merge：collect 基础上，把各 branch 的 dict 输出浅合并 → 额外给 merged 字段
    race：返回**最先成功**的分支，取消其余 → {winner, output, branch_runs}

output（collect / merge）：
    {
      "branches": {key: branch_output, ...},
      "merged": {...},                # 仅 merge
      "branch_runs": [{key, ok, started_offset_ms, duration_ms, error?}, ...],
    }
branch_runs 带每条分支相对节点起点的 offset + 时长 —— 供 Trace Gantt 看并发重叠。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.nodes._subgraph import ensure_nest_depth, run_subgraph
from chameleon.core.graph.registry import register_node_type

_JOIN_STRATEGIES = ("collect", "merge", "race")
#: 并发分支数上限
MAX_BRANCHES = 20


class ParallelNode(Node[Any, dict]):
    """fork-join 并发分支节点"""

    type = "parallel"

    def validate_data(self, data: dict[str, Any]) -> None:
        branches = data.get("branches")
        if not isinstance(branches, list) or len(branches) < 2:
            raise ValueError("ParallelNode.data.branches 至少 2 条分支")
        if len(branches) > MAX_BRANCHES:
            raise ValueError(
                f"ParallelNode.data.branches 至多 {MAX_BRANCHES} 条"
            )
        keys: set[str] = set()
        for b in branches:
            if not isinstance(b, dict):
                raise ValueError("ParallelNode 每条 branch 必须是 dict")
            key = b.get("key")
            if not key or not isinstance(key, str):
                raise ValueError("ParallelNode branch.key 必填（非空 string）")
            if key in keys:
                raise ValueError(f"ParallelNode branch.key 重复: {key}")
            keys.add(key)
            body = b.get("body")
            if not isinstance(body, dict):
                raise ValueError(
                    f"ParallelNode branch[{key}].body 必填（子图 GraphSpec dict）"
                )
            try:
                from chameleon.core.graph.engine import Orchestrator
                from chameleon.core.graph.types import GraphSpec

                Orchestrator(GraphSpec.model_validate(body))
            except Exception as e:  # noqa: BLE001
                raise ValueError(
                    f"ParallelNode branch[{key}].body 非法子图: {e}"
                ) from e

        js = data.get("join_strategy", "collect")
        if js not in _JOIN_STRATEGIES:
            raise ValueError(
                f"ParallelNode.data.join_strategy 必须是 {_JOIN_STRATEGIES} 之一"
            )

        c = data.get("concurrency")
        if c is not None and (not isinstance(c, int) or c < 1):
            raise ValueError("ParallelNode.data.concurrency 必须 ≥ 1 整数")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        ensure_nest_depth(ctx, "ParallelNode")

        from chameleon.core.graph.types import GraphSpec

        branches = self.spec.data["branches"]
        join = self.spec.data.get("join_strategy", "collect")
        concurrency = int(self.spec.data.get("concurrency") or len(branches))
        sem = asyncio.Semaphore(concurrency)
        node_start = time.monotonic()

        logger.info(
            "parallel {} | branches={} | join={} | concurrency={}",
            self.id,
            len(branches),
            join,
            concurrency,
        )

        async def _run_branch(b: dict) -> dict[str, Any]:
            key = b["key"]
            body_spec = GraphSpec.model_validate(b["body"])
            offset_ms = int((time.monotonic() - node_start) * 1000)
            started = time.monotonic()
            async with sem:
                res = await run_subgraph(
                    ctx, body_spec, input, request_suffix=f"branch.{key}"
                )
            return {
                "key": key,
                "result": res,
                "started_offset_ms": offset_ms,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        if join == "race":
            return await self._join_race(branches, _run_branch)
        return self._join_collect(
            await asyncio.gather(*(_run_branch(b) for b in branches)),
            merge=(join == "merge"),
        )

    # ── collect / merge：等全部成功 ────────────────────────

    def _join_collect(
        self, branch_results: list[dict[str, Any]], *, merge: bool
    ) -> dict:
        outputs: dict[str, Any] = {}
        branch_runs: list[dict[str, Any]] = []
        for br in branch_results:
            res = br["result"]
            ok = res.status.value == "success"
            branch_runs.append(
                {
                    "key": br["key"],
                    "ok": ok,
                    "started_offset_ms": br["started_offset_ms"],
                    "duration_ms": br["duration_ms"],
                    "error": res.error,
                }
            )
            if not ok:
                err = res.error or {}
                raise RuntimeError(
                    f"parallel 分支[{br['key']}]失败: "
                    f"{err.get('type')}: {err.get('message')}"
                )
            outputs[br["key"]] = res.output

        out: dict[str, Any] = {"branches": outputs, "branch_runs": branch_runs}
        if merge:
            merged: dict[str, Any] = {}
            for br in branch_results:  # 按分支声明顺序合并；后者覆盖同名键
                o = outputs[br["key"]]
                if isinstance(o, dict):
                    merged.update(o)
            out["merged"] = merged
        return out

    # ── race：最先成功者胜，取消其余 ──────────────────────

    async def _join_race(self, branches: list, run_branch) -> dict:
        tasks = {
            asyncio.create_task(run_branch(b)): b["key"] for b in branches
        }
        pending = set(tasks)
        winner: dict[str, Any] | None = None
        branch_runs: list[dict[str, Any]] = []
        try:
            while pending and winner is None:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for t in done:
                    br = t.result()
                    res = br["result"]
                    ok = res.status.value == "success"
                    branch_runs.append(
                        {
                            "key": br["key"],
                            "ok": ok,
                            "started_offset_ms": br["started_offset_ms"],
                            "duration_ms": br["duration_ms"],
                            "error": res.error,
                        }
                    )
                    if ok and winner is None:
                        winner = br
        finally:
            for t in pending:
                t.cancel()

        if winner is None:
            raise RuntimeError("parallel race：所有分支都失败")
        return {
            "winner": winner["key"],
            "output": winner["result"].output,
            "branch_runs": branch_runs,
        }


register_node_type(ParallelNode)
