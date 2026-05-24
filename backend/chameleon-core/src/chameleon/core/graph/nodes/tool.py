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

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.registry import register_node_type
from chameleon.core.graph.node_base import Node
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import ToolInstance
from chameleon.core.tools import (
    Tool,
    ToolContext,
    ToolResult,
    get_tool_class,
)
from chameleon.core.tools.registry import register_tool as _register_tool_real


def register_tool(tool_cls):  # noqa: ANN001
    """转发到 chameleon.core.tools.registry.register_tool

    兼容老测试 / 早期代码直接从本模块 import register_tool 的写法。
    """
    return _register_tool_real(tool_cls)


class ToolNode(Node[Any, dict]):
    """调注册 Tool"""

    type = "tool"

    def validate_data(self, data: dict[str, Any]) -> None:
        tk = data.get("tool_key")
        if not tk or not isinstance(tk, str):
            raise ValueError("ToolNode.data.tool_key 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        tk = self.spec.data["tool_key"]
        tool_cls = get_tool_class(tk)
        if tool_cls is None:
            raise RuntimeError(
                f"tool_key={tk!r} 未注册；可用 keys 由启动期 builtins 扫表得"
            )

        # 查 admin 配的 tool_instances 实例（含 config + enabled）
        config: dict[str, Any] = {}
        if _is_real_tool(tool_cls):
            inst = await _load_tool_instance(tk)
            if inst is not None and not inst.enabled:
                return {
                    "tool_key": tk,
                    "ok": False,
                    "data": None,
                    "error": f"tool {tk!r} 被 admin 禁用",
                    "meta": {"instance_id": inst.id},
                }
            if inst is not None:
                config = inst.config or {}
            # spec.data.config 仍能覆盖（同名字段）
            if self.spec.data.get("config"):
                config = {**config, **self.spec.data["config"]}
        else:
            config = self.spec.data.get("config") or {}

        # 实例化兼容两种形态：真 Tool 子类 / 老 duck-typed 类
        try:
            tool = tool_cls(config) if _is_real_tool(tool_cls) else tool_cls()
        except TypeError:
            tool = tool_cls()

        args = dict(self.spec.data.get("args") or {})
        if isinstance(input, dict):
            # input 字段被 data.args 覆盖（admin 优先）
            args = {**input, **args}

        tool_ctx = ToolContext(
            caller="graph",
            related_id=str(ctx.graph_run_id),
            extra={"graph_id": ctx.graph_id, "node_id": self.id},
        )

        if _is_real_tool(tool_cls):
            result = await tool.run_with_validation(args, tool_ctx)
            return {
                "tool_key": tk,
                "ok": result.ok,
                "data": result.data,
                "error": result.error,
                "meta": result.meta,
            }

        # 兼容老 duck-typed Tool：直接调 run，结果整体返回
        legacy = await tool.run(args, tool_ctx)
        return {"tool_key": tk, "result": legacy}


def _is_real_tool(cls: type) -> bool:
    """检测是否真正继承 chameleon.core.tools.Tool 基类"""
    try:
        return issubclass(cls, Tool)
    except TypeError:
        return False


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
