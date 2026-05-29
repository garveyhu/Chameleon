"""tools admin service —— CRUD + 与代码层 registry 对齐"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.data.models import ToolInstance
from chameleon.integrations.tools import all_tool_classes, get_tool_class
from chameleon.system.tools.schemas import (
    CreateToolInstanceRequest,
    ToolCatalogItem,
    ToolInstanceItem,
    UpdateToolInstanceRequest,
)


async def list_instances(
    session: AsyncSession,
) -> list[ToolInstanceItem]:
    rows = (
        (
            await session.execute(
                select(ToolInstance).order_by(ToolInstance.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [ToolInstanceItem.model_validate(r) for r in rows]


async def get_instance(
    session: AsyncSession, instance_id: int
) -> ToolInstanceItem:
    row = await _load(session, instance_id)
    return ToolInstanceItem.model_validate(row)


async def create_instance(
    session: AsyncSession, req: CreateToolInstanceRequest
) -> ToolInstanceItem:
    cls = get_tool_class(req.tool_key)
    if cls is None:
        raise ValidationError(
            message=(
                f"tool_key={req.tool_key!r} 未注册；"
                f"已注册：{sorted(all_tool_classes().keys())}"
            )
        )
    dup = (
        await session.execute(
            select(ToolInstance.id).where(ToolInstance.tool_key == req.tool_key)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValidationError(
            message=f"tool_key={req.tool_key} 已配过实例，请改用 update"
        )

    row = ToolInstance(
        tool_key=req.tool_key,
        name=req.name,
        description=req.description,
        config=req.config,
        enabled=cls.default_enabled,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = ToolInstanceItem.model_validate(row)
    await session.commit()
    return item


async def update_instance(
    session: AsyncSession,
    instance_id: int,
    req: UpdateToolInstanceRequest,
) -> ToolInstanceItem:
    row = await _load(session, instance_id)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.config is not None:
        row.config = req.config
    if req.enabled is not None:
        row.enabled = req.enabled
    await session.flush()
    await session.refresh(row)
    item = ToolInstanceItem.model_validate(row)
    await session.commit()
    return item


async def delete_instance(session: AsyncSession, instance_id: int) -> None:
    row = await _load(session, instance_id)
    await session.execute(
        delete(ToolInstance).where(ToolInstance.id == row.id)
    )
    await session.commit()


async def list_catalog(session: AsyncSession) -> list[ToolCatalogItem]:
    """合并代码层注册的内置 tools + DB 持久化的实例

    每个内置 tool 一条 catalog；instance_id / enabled 反映 admin 当前配置。
    """
    instances = (
        (await session.execute(select(ToolInstance))).scalars().all()
    )
    by_key = {i.tool_key: i for i in instances}

    out: list[ToolCatalogItem] = []
    for key, cls in all_tool_classes().items():
        # 容忍非 Tool 子类（测试用 duck-typed stub 也会注册到 registry）
        try:
            tool = cls()
            schema = (
                tool.parameters_schema()
                if hasattr(tool, "parameters_schema")
                else {"type": "object", "properties": {}}
            )
        except Exception:  # noqa: BLE001
            schema = {"type": "object", "properties": {}}
        inst = by_key.get(key)
        out.append(
            ToolCatalogItem(
                tool_key=key,
                description=getattr(cls, "description", ""),
                parameters_schema=schema,
                default_enabled=getattr(cls, "default_enabled", True),
                instance_id=inst.id if inst else None,
                instance_enabled=inst.enabled if inst else None,
            )
        )
    return sorted(out, key=lambda x: x.tool_key)


async def get_enabled_instance(
    session: AsyncSession, tool_key: str
) -> ToolInstance | None:
    """ToolNode 跑时用：拿 enabled 的实例；找不到 / 禁用 → None"""
    row = (
        await session.execute(
            select(ToolInstance).where(
                ToolInstance.tool_key == tool_key,
                ToolInstance.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    return row


# ── helpers ───────────────────────────────────────────────


async def _load(
    session: AsyncSession, instance_id: int
) -> ToolInstance:
    row = (
        await session.execute(
            select(ToolInstance).where(ToolInstance.id == instance_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"tool_instance 不存在: {instance_id}"
        )
    return row
