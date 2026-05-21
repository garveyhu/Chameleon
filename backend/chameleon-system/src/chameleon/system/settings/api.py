"""settings HTTP 路由

挂点：/v1/admin/settings/*
鉴权：必须 admin 角色（settings 涉及敏感导出 / 导入操作）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import ValidationError
from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import (
    CurrentUser,
    require_role,
)
from chameleon.system.settings.export_service import build_export_zip
from chameleon.system.settings.import_service import apply_import_zip

router = APIRouter(prefix="/v1/admin/settings", tags=["admin:settings"])


@router.post(
    "/export-json",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def export_json(
    session: AsyncSession = Depends(get_session),
    _: CurrentUser = Depends(require_role("admin")),
) -> Response:
    """导出全 DB 配置为 zip（仅 admin）"""
    zip_bytes, filename = await build_export_zip(session)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
        },
    )


@router.post("/import-json", response_model=Result[dict])
async def import_json(
    file: UploadFile = File(...),
    confirm: bool = Form(False),
    session: AsyncSession = Depends(get_session),
    _: CurrentUser = Depends(require_role("admin")),
) -> Result[dict]:
    """从 zip 还原配置（仅 admin，要 confirm=true 防误操作）"""
    if not confirm:
        raise ValidationError(message="导入是危险操作，必须传 confirm=true")
    raw = await file.read()
    if not raw:
        raise ValidationError(message="上传文件为空")
    summary = await apply_import_zip(session, raw)
    await session.commit()
    return Result.ok(summary.to_dict())
