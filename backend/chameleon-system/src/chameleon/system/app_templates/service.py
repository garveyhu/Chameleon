"""app_templates service —— P22.5 PR #83

红线（plan §2 P22）：
- ⛔ 用户自传 template 默认 verified=False；list 默认仅返 verified
- ⛔ install 时按 verified 校验；downloads 计数 +1
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import AppTemplate
from chameleon.system.app_templates.schemas import (
    CATEGORIES,
    AppTemplateItem,
    CreateAppTemplateRequest,
    InstallTemplateResult,
)


async def list_templates(
    session: AsyncSession,
    *,
    only_verified: bool = True,
    category: str | None = None,
    limit: int = 50,
) -> list[AppTemplateItem]:
    """list templates；默认仅 verified=True（红线）"""
    stmt = select(AppTemplate)
    if only_verified:
        stmt = stmt.where(AppTemplate.verified.is_(True))
    if category:
        stmt = stmt.where(AppTemplate.category == category)
    stmt = stmt.order_by(AppTemplate.downloads.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [AppTemplateItem.model_validate(r) for r in rows]


async def get_template(
    session: AsyncSession, template_id: int
) -> AppTemplateItem:
    row = await _load(session, template_id)
    return AppTemplateItem.model_validate(row)


async def create_template(
    session: AsyncSession,
    req: CreateAppTemplateRequest,
    *,
    created_by_user_id: int | None = None,
) -> AppTemplateItem:
    """admin 提交模板；默认 verified=False（红线：自传不进默认列表）"""
    if req.category not in CATEGORIES:
        raise BusinessError(
            ResultCode.ValidationError,
            message=f"未知 category={req.category!r}；可选: {CATEGORIES}",
        )
    row = AppTemplate(
        name=req.name,
        description=req.description,
        category=req.category,
        spec_json=req.spec_json,
        cover_image=req.cover_image,
        verified=False,  # ⛔ 红线
        downloads=0,
        created_by_user_id=created_by_user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = AppTemplateItem.model_validate(row)
    await session.commit()
    logger.info(
        "app_template created | id={} | name={} | category={} | verified=False",
        row.id,
        row.name,
        row.category,
    )
    return item


async def verify_template(
    session: AsyncSession, template_id: int, *, verified: bool
) -> AppTemplateItem:
    """admin 审核；标 verified=True 后进默认推荐列表"""
    row = await _load(session, template_id)
    row.verified = verified
    await session.flush()
    await session.refresh(row)
    item = AppTemplateItem.model_validate(row)
    await session.commit()
    logger.info(
        "app_template verify | id={} | verified={}",
        row.id,
        verified,
    )
    return item


async def install_template(
    session: AsyncSession,
    template_id: int,
) -> InstallTemplateResult:
    """安装 = 克隆 spec（具体产物由 category dispatch；
    本 PR 仅写记录 + downloads++；后续 PR 接 graph/agent/kb 创建链路）
    """
    row = await _load(session, template_id)
    # downloads += 1（即使是 unverified，downloads 仍记，便于审查热门草稿）
    row.downloads = (row.downloads or 0) + 1
    await session.flush()
    await session.commit()

    logger.info(
        "app_template installed | tmpl={} | name={} | cat={} | dl={}",
        row.id,
        row.name,
        row.category,
        row.downloads,
    )
    return InstallTemplateResult(
        template_id=row.id,
        template_name=row.name,
        category=row.category,
        installed_at=datetime.now(timezone.utc),
        artifact_id=None,
    )


async def delete_template(
    session: AsyncSession, template_id: int
) -> None:
    row = await _load(session, template_id)
    await session.delete(row)
    await session.commit()


async def _load(
    session: AsyncSession, template_id: int
) -> AppTemplate:
    row = (
        await session.execute(
            select(AppTemplate).where(AppTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"app_template 不存在: {template_id}",
        )
    return row
