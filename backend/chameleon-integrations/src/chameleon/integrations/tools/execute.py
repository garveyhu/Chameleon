"""工具执行入口 —— graph ToolNode / LLM function-calling / agentkit 共用。

把 `run_tool` 从 `engine/graph/nodes/tool.py` 下沉到 integrations，使其不再绑死
graph：它本就只依赖 core（协议 + observe 类型）+ data（tool_instances admin config）+
integrations（registry + observe aspect），与 graph 无关。

流程：get_tool_class → 查 tool_instances admin config（含 enabled 闸门）→
实例化 → run_with_validation（按 parameters_schema 校验入参）→ 统一 dict 结果。
执行点包 record_scope 落 TOOL 观测，一处覆盖所有工具调用路径。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from chameleon.core.observe.context import ObservationType
from chameleon.core.tools import ToolContext
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import ToolInstance
from chameleon.integrations.observe.aspect import record_scope
from chameleon.integrations.tools.registry import get_tool_class


async def run_tool(
    tool_key: str,
    args: dict[str, Any],
    *,
    caller: str,
    related_id: str | None = None,
    extra: dict[str, Any] | None = None,
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按 tool_key 跑一个注册 Tool，返回统一 dict 结果。

    Args:
        tool_key: 注册的 tool key
        args: 调用参数（已合并好）
        caller: ToolContext.caller（如 "graph" / "llm-node" / "agentkit"）
        related_id: ToolContext.related_id（如 graph_run_id / request_id）
        extra: ToolContext.extra（graph_id / node_id / agent_key 等）
        config_override: 覆盖 admin config 的同名字段

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

    # Tool 是自定义 ABC（非 LangChain BaseTool）→ 执行点包 record_scope 落 TOOL 节点。
    # graph ToolNode / LLMNode function-calling / agentkit 共用此入口，一处覆盖全工具路径。
    async with record_scope(
        observation_type=ObservationType.TOOL,
        name=tool_key,
        request_payload={"tool_key": tool_key, "args": str(args)[:2000]},
    ) as scope:
        result = await tool.run_with_validation(args, tool_ctx)
        scope.success = bool(result.ok)
        if not result.ok:
            scope.code = 500
            scope.error_message = (result.error or "")[:500]
        scope.response_payload = {
            "ok": result.ok,
            "data": str(result.data)[:2000] if result.data is not None else None,
            "error": result.error,
        }
        return {
            "tool_key": tool_key,
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
            "meta": result.meta,
        }


async def _load_tool_instance(tool_key: str) -> ToolInstance | None:
    """查 tool_instances 表的 admin 配置（独立 session）。"""
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                select(ToolInstance).where(ToolInstance.tool_key == tool_key)
            )
        ).scalar_one_or_none()
