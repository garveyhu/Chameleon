"""ToolNode —— 调注册的 Tool（P18.2 起接 chameleon.core.tools 实现）

data 配置（v0.4 起）：
    {
      "tool_key": "http",
      "args": { ... }       # 透传给 Tool.run；也可以从上游 input 拼
    }

执行约定（P18.2 PR #23）：
    1. 从 chameleon.core.tools.get_tool_class(tool_key) 拿 Tool 子类
    2. 查 tool_instances 表的 admin config（同步路径用独立 session）
       - 找到且 enabled=True → 用 admin config 实例化
       - 找到但 enabled=False → 拒绝 + 清晰错误
       - 未找到（admin 没配过）→ 用代码层默认（空 config）
    3. 用 run_with_validation 跑（按 parameters_schema 校验入参）
    4. 返 {tool_key, ok, data, error, meta}

兼容：register_tool() 函数本地也透出，方便测试 / 早期模块手动注册。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from chameleon.core.tools import ToolContext, ToolResult  # 协议留 core
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import ToolInstance
from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type
from chameleon.integrations.tools import (  # registry 已迁 integrations
    get_tool_class,
)
from chameleon.integrations.tools import (
    register_tool as _register_tool_real,
)


def register_tool(tool_cls):  # noqa: ANN001
    """转发到 chameleon.integrations.tools.registry.register_tool

    兼容老测试 / 早期代码直接从本模块 import register_tool 的写法。
    """
    return _register_tool_real(tool_cls)


async def run_tool(
    tool_key: str,
    args: dict[str, Any],
    *,
    caller: str,
    related_id: str | None = None,
    extra: dict[str, Any] | None = None,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 tool_key 跑一个注册 Tool，返回统一 dict 结果

    ToolNode 与 LLMNode 的多轮 tool_call 循环（A2）共用此入口，避免逻辑分叉。

    流程：get_tool_class → 查 tool_instances admin config（含 enabled 闸门）→
    实例化 → run_with_validation（按 parameters_schema 校验入参）。

    Args:
        tool_key: 注册的 tool key
        args: 调用参数（已合并好）
        caller: ToolContext.caller（如 "graph" / "llm-node"）
        related_id: ToolContext.related_id（如 graph_run_id）
        extra: ToolContext.extra（graph_id / node_id 等）
        config_override: 覆盖 admin config 的同名字段（spec.data.config）

    Returns:
        {tool_key, ok, data, error, meta}
        admin 禁用：{tool_key, ok: False, error: "...被 admin 禁用", meta}
    """
    tool_cls = get_tool_class(tool_key)
    if tool_cls is None:
        raise RuntimeError(
            f"tool_key={tool_key!r} 未注册；可用 keys 由启动期 builtins 扫表得"
        )

    config: dict[str, Any] = {}
    inst = await _load_tool_instance(tool_key)
    if inst is not None and not inst.enabled:
        return {
            "tool_key": tool_key,
            "ok": False,
            "data": None,
            "error": f"tool {tool_key!r} 被 admin 禁用",
            "meta": {"instance_id": inst.id},
        }
    if inst is not None:
        config = inst.config or {}
    if config_override:
        config = {**config, **config_override}

    tool = tool_cls(config)

    tool_ctx = ToolContext(
        caller=caller,
        related_id=related_id,
        extra=extra or {},
    )

    result = await tool.run_with_validation(args, tool_ctx)
    return {
        "tool_key": tool_key,
        "ok": result.ok,
        "data": result.data,
        "error": result.error,
        "meta": result.meta,
    }


class ToolNode(Node[Any, dict]):
    """调注册 Tool"""

    type = "tool"

    def validate_data(self, data: dict[str, Any]) -> None:
        tk = data.get("tool_key")
        if not tk or not isinstance(tk, str):
            raise ValueError("ToolNode.data.tool_key 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        tk = self.spec.data["tool_key"]

        args = dict(self.spec.data.get("args") or {})
        if isinstance(input, dict):
            # input 字段被 data.args 覆盖（admin 优先）
            args = {**input, **args}

        return await run_tool(
            tk,
            args,
            caller="graph",
            related_id=str(ctx.graph_run_id),
            extra={"graph_id": ctx.graph_id, "node_id": self.id},
            config_override=self.spec.data.get("config"),
        )


async def _load_tool_instance(tool_key: str) -> ToolInstance | None:
    """查 tool_instances 表的 admin 配置（独立 session）"""
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(ToolInstance).where(ToolInstance.tool_key == tool_key)
            )
        ).scalar_one_or_none()


# 防 lint：ToolResult 在模块层 import 后未直接使用，但暴露给 type-checkers / docs
_ = ToolResult


register_node_type(ToolNode)
