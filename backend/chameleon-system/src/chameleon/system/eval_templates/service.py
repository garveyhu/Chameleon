"""eval_templates service —— P21.2 PR #62

红线（plan §2 P21）：
- ⛔ template 改动 → version += 1；老 EvalJob 引用 freeze 版本不变
- ⛔ 同 (workspace, name) 不同 version 共存（unique key 含 version）
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import EvalTemplate
from chameleon.system.eval_templates.schemas import (
    CreateEvalTemplateRequest,
    EvalTemplateItem,
    UpdateEvalTemplateRequest,
)


async def list_templates(
    session: AsyncSession, workspace_id: int | None = None
) -> list[EvalTemplateItem]:
    """列所有模板（同 name 只返最新 version；老 version 隐式留给 freeze 引用）"""
    stmt = select(EvalTemplate)
    if workspace_id is not None:
        stmt = stmt.where(EvalTemplate.workspace_id == workspace_id)
    stmt = stmt.order_by(
        EvalTemplate.name.asc(), EvalTemplate.version.desc()
    )
    rows = (await session.execute(stmt)).scalars().all()

    seen: set[tuple[int | None, str]] = set()
    latest: list[EvalTemplate] = []
    for r in rows:
        key = (r.workspace_id, r.name)
        if key in seen:
            continue
        seen.add(key)
        latest.append(r)
    return [EvalTemplateItem.model_validate(r) for r in latest]


async def get_template(
    session: AsyncSession, template_id: int
) -> EvalTemplateItem:
    row = await _load(session, template_id)
    return EvalTemplateItem.model_validate(row)


async def get_template_by_version(
    session: AsyncSession, name: str, version: int, workspace_id: int | None
) -> EvalTemplateItem:
    """精确取某 version（freeze 引用用）"""
    row = (
        await session.execute(
            select(EvalTemplate).where(
                EvalTemplate.name == name,
                EvalTemplate.version == version,
                EvalTemplate.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"eval_template name={name} version={version} 不存在",
        )
    return EvalTemplateItem.model_validate(row)


async def create_template(
    session: AsyncSession,
    req: CreateEvalTemplateRequest,
    workspace_id: int | None = None,
) -> EvalTemplateItem:
    """同 (workspace, name) 已存在 → 拒绝（要新 version 走 update）"""
    existing = (
        await session.execute(
            select(EvalTemplate).where(
                EvalTemplate.name == req.name,
                EvalTemplate.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"eval_template name={req.name} 已存在；要改走 update（自动 version+=1）",
        )

    row = EvalTemplate(
        name=req.name,
        description=req.description,
        metrics=[m.model_dump() for m in req.metrics],
        judge_provider=req.judge_provider,
        version=1,
        workspace_id=workspace_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = EvalTemplateItem.model_validate(row)
    await session.commit()
    logger.info(
        "eval_template created | id={} | name={} | version=1",
        row.id,
        row.name,
    )
    return item


async def update_template(
    session: AsyncSession,
    template_id: int,
    req: UpdateEvalTemplateRequest,
) -> EvalTemplateItem:
    """改动 → 创建 version+=1 的新行；老行保留（freeze 引用源）

    红线：每次 update 都新建行，不原地改；让老 EvalJob 引用 frozen 版本不变。
    """
    old = await _load(session, template_id)
    new_metrics = (
        [m.model_dump() for m in req.metrics]
        if req.metrics is not None
        else list(old.metrics or [])
    )
    new_desc = req.description if req.description is not None else old.description
    new_judge = (
        req.judge_provider
        if req.judge_provider is not None
        else old.judge_provider
    )

    row = EvalTemplate(
        name=old.name,
        description=new_desc,
        metrics=new_metrics,
        judge_provider=new_judge,
        version=old.version + 1,
        workspace_id=old.workspace_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = EvalTemplateItem.model_validate(row)
    await session.commit()
    logger.info(
        "eval_template updated | id={} | name={} | version={} -> {}",
        row.id,
        row.name,
        old.version,
        row.version,
    )
    return item


async def delete_template(
    session: AsyncSession, template_id: int
) -> None:
    """删除单个 version 行（不级联同 name 其它 version；老 job freeze 依然可读其引用的 frozen 版本）"""
    row = await _load(session, template_id)
    await session.execute(
        delete(EvalTemplate).where(EvalTemplate.id == row.id)
    )
    await session.commit()


async def _load(
    session: AsyncSession, template_id: int
) -> EvalTemplate:
    row = (
        await session.execute(
            select(EvalTemplate).where(EvalTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"eval_template 不存在: {template_id}",
        )
    return row
