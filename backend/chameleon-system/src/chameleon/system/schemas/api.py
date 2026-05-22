"""schemas HTTP 路由 (/v1/admin/schemas)

提供两个端点：
- GET /v1/admin/schemas              列出所有已注册 schema name + 简要元信息
- GET /v1/admin/schemas/{name}       拿单个 schema dump（标准 JSON Schema）

前端动态表单组件按需调，不主动预拉。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import Result
from chameleon.core.schema import dump_schema_by_name, list_all
from chameleon.system.auth.dependencies import require_permission


class SchemaListItem(BaseModel):
    """schema 列表元信息（不含 schema 内容，只列名）"""

    name: str = Field(..., description="schema 注册 name，按 `<domain>.<sub>.<purpose>` 约定")
    title: str | None = Field(None, description="Pydantic 类 docstring 首行或类名")
    qualified_name: str = Field(..., description="完整 `<module>.<class>` 便于追踪")


router = APIRouter(prefix="/v1/admin/schemas", tags=["admin:schemas"])


@router.get("", response_model=Result[list[SchemaListItem]])
async def list_schemas(
    prefix: str | None = Query(default=None, description="按 name 前缀过滤"),
    _: object = Depends(require_permission("schemas:read")),
) -> Result[list[SchemaListItem]]:
    """列出已注册 schema name。"""
    items: list[SchemaListItem] = []
    for name, cls in list_all().items():
        if prefix and not name.startswith(prefix):
            continue
        title = _first_doc_line(cls.__doc__) or cls.__name__
        items.append(
            SchemaListItem(
                name=name,
                title=title,
                qualified_name=f"{cls.__module__}.{cls.__name__}",
            )
        )
    items.sort(key=lambda x: x.name)
    return Result.ok(items)


@router.get("/{name}", response_model=Result[dict])
async def get_schema(
    name: str,
    inline_refs: bool = Query(
        default=False,
        description="True 时把 $defs/$ref 内联进主 schema，方便直接渲染",
    ),
    _: object = Depends(require_permission("schemas:read")),
) -> Result[dict]:
    """按 name 取单个 schema dump。"""
    schema = dump_schema_by_name(name, inline_refs=inline_refs)
    if schema is None:
        raise BusinessError(
            ResultCode.AgentNotFound,
            message=f"schema 不存在: {name}",
        )
    return Result.ok(schema)


def _first_doc_line(doc: str | None) -> str | None:
    if not doc:
        return None
    for line in doc.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return None
