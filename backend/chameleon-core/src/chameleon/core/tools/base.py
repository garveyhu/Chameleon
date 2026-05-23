"""Tool 协议 —— graph ToolNode / LLM function calling 共用入口

设计参考 OpenAI function calling：
- tool_key：调用方在 spec / function_call 里引用
- description：给 LLM 看的工具说明
- parameters_schema：JSON Schema dict，描述 args 结构
- async run(args, ctx)：实际执行，返 JSON-serializable

红线（P18 §2 新增）：
- 不能持 db session；要数据走 service 层依赖注入
- 不直接 import 业务模块 service —— 避免反向依赖
- 重型 / 不安全的 tool（SQL / Code）必须默认 disabled，admin 显式启
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolContext(BaseModel):
    """Tool.run() 调用上下文（只读）"""

    model_config = ConfigDict(frozen=True)

    # 调用方身份（graph_run_id / user_id / app_id 之一）
    caller: str = "system"
    # 可选关联 ID（graph node 调用时 = graph_run_id）
    related_id: str | None = None
    # 调用方传 / 业务自定义
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Tool.run() 标准返回"""

    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] | None = None


class Tool(ABC):
    """工具协议基类

    子类必须：
    - 类属性 `tool_key`（独一无二）+ `description`
    - 实现 `parameters_schema` 返 JSON Schema
    - 实现 `async run(args, ctx) -> ToolResult`

    Args 校验：基类 `run_with_validation` 自动按 parameters_schema 验入参后调 run。
    """

    #: 子类必须覆盖；与 registry key 一致
    tool_key: str = ""

    #: 给 LLM / admin UI 看的简短描述
    description: str = ""

    #: 是否默认启用（不安全的工具如 SQL/Code 默认 False）
    default_enabled: bool = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """返参数 JSON Schema dict（type:object + properties + required）"""
        raise NotImplementedError

    @abstractmethod
    async def run(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        """执行；异常应转 ToolResult(ok=False, error=...)，不要 raise"""
        raise NotImplementedError

    async def run_with_validation(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        """带 JSON Schema 校验的入口（推荐 graph ToolNode 用这个）"""
        try:
            _validate_args(args, self.parameters_schema())
        except ValueError as e:
            return ToolResult(ok=False, error=f"args 校验失败: {e}")
        try:
            return await self.run(args, ctx)
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False, error=f"{type(e).__name__}: {str(e)[:300]}"
            )


# ── 极简 JSON Schema 校验（避免依赖 jsonschema） ─────────────


def _validate_args(args: dict[str, Any], schema: dict[str, Any]) -> None:
    """支持 type:object + properties[name].type + required[] 子集

    完整 JSON Schema 留给 P19 引入 jsonschema 依赖；目前只校
    Tool 实际用到的简单形态。
    """
    if not isinstance(args, dict):
        raise ValueError(f"args 必须是 dict，得到 {type(args).__name__}")

    props = schema.get("properties", {})
    required = schema.get("required", [])
    for k in required:
        if k not in args:
            raise ValueError(f"缺少必填字段: {k}")

    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for k, v in args.items():
        if k not in props:
            continue  # 容忍未声明字段（Tool 自己决定要不要用）
        spec = props[k]
        t = spec.get("type")
        if t and t in type_map and not isinstance(v, type_map[t]):
            raise ValueError(
                f"字段 {k} 类型不匹配：需 {t}, 实际 {type(v).__name__}"
            )
        enum = spec.get("enum")
        if enum is not None and v not in enum:
            raise ValueError(f"字段 {k} 必须在 {enum} 中")
