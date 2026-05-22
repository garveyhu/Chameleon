"""settings HTTP 路由

挂点：/v1/admin/settings/*
鉴权：
  - system_settings/model_defaults CRUD：settings:read/write
  - export/import：必须 admin 角色（涉及敏感导出操作）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode, ValidationError
from chameleon.core.api.response import Result
from chameleon.core.config.system_settings_schema import (
    SYSTEM_SETTINGS_SCHEMA,
    schema_dict,
)
from chameleon.core.infra.db import get_session
from chameleon.core.models import LLMModel, ModelDefault, Setting
from chameleon.system.auth.dependencies import (
    CurrentUser,
    require_permission,
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


# ── 系统运行时设置 (settings 表，scope='global') ────────────────


class SystemSettingItem(BaseModel):
    key: str
    group: str
    value_type: str
    value: Any
    default: Any
    min: float | None = None
    max: float | None = None
    select_options: list[str] = []
    description_zh: str = ""
    description_en: str = ""


class SystemSettingsResponse(BaseModel):
    items: list[SystemSettingItem]


def _unwrap_value(raw: Any) -> Any:
    """settings.value 列实际存 {"v": <真实值>}（JSON 列要求 dict），读取时拆包。"""
    if isinstance(raw, dict) and set(raw.keys()) == {"v"}:
        return raw["v"]
    return raw


def _wrap_value(value: Any) -> dict:
    return {"v": value}


@router.get("/system", response_model=Result[SystemSettingsResponse])
async def list_system_settings(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:read")),
) -> Result[SystemSettingsResponse]:
    """返回 schema 全集 + DB 当前值（DB 缺失时 value=default）"""
    rows = (
        (await session.execute(select(Setting).where(Setting.scope == "global")))
        .scalars()
        .all()
    )
    db_values = {r.key: _unwrap_value(r.value) for r in rows}
    items = [
        SystemSettingItem(
            key=s.key,
            group=s.group,
            value_type=s.value_type,
            value=db_values.get(s.key, s.default),
            default=s.default,
            min=s.min,
            max=s.max,
            select_options=list(s.select_options),
            description_zh=s.description_zh,
            description_en=s.description_en,
        )
        for s in SYSTEM_SETTINGS_SCHEMA
    ]
    return Result.ok(SystemSettingsResponse(items=items))


class UpdateSettingRequest(BaseModel):
    value: Any


@router.post("/system/{key}/update", response_model=Result[SystemSettingItem])
async def update_system_setting(
    key: str,
    req: UpdateSettingRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:write")),
) -> Result[SystemSettingItem]:
    schema_map = schema_dict()
    s = schema_map.get(key)
    if s is None:
        raise ValidationError(message=f"unknown setting key: {key}")

    value = req.value
    # 基础类型校验
    if s.value_type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(message=f"{key} 需要整数")
        if s.min is not None and value < s.min:
            raise ValidationError(message=f"{key} 不能小于 {s.min}")
        if s.max is not None and value > s.max:
            raise ValidationError(message=f"{key} 不能大于 {s.max}")
    elif s.value_type == "bool":
        if not isinstance(value, bool):
            raise ValidationError(message=f"{key} 需要 true/false")
    elif s.value_type == "select":
        if value not in s.select_options:
            raise ValidationError(
                message=f"{key} 必须为 {s.select_options} 之一"
            )

    existing = (
        await session.execute(
            select(Setting).where(Setting.scope == "global", Setting.key == key)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Setting(
                scope="global",
                key=key,
                value=_wrap_value(value),
                value_type=s.value_type,
                description=f"[{s.group}] {s.description_zh}",
            )
        )
    else:
        existing.value = _wrap_value(value)
        existing.value_type = s.value_type
    await session.commit()
    logger.info("system_setting updated: {} = {!r}", key, value)
    return Result.ok(
        SystemSettingItem(
            key=key,
            group=s.group,
            value_type=s.value_type,
            value=value,
            default=s.default,
            min=s.min,
            max=s.max,
            select_options=list(s.select_options),
            description_zh=s.description_zh,
            description_en=s.description_en,
        )
    )


@router.post("/system/{key}/reset", response_model=Result[SystemSettingItem])
async def reset_system_setting(
    key: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:write")),
) -> Result[SystemSettingItem]:
    schema_map = schema_dict()
    s = schema_map.get(key)
    if s is None:
        raise ValidationError(message=f"unknown setting key: {key}")
    existing = (
        await session.execute(
            select(Setting).where(Setting.scope == "global", Setting.key == key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.commit()
    return Result.ok(
        SystemSettingItem(
            key=key,
            group=s.group,
            value_type=s.value_type,
            value=s.default,
            default=s.default,
            min=s.min,
            max=s.max,
            select_options=list(s.select_options),
            description_zh=s.description_zh,
            description_en=s.description_en,
        )
    )


# ── 默认模型映射 (model_defaults 表) ───────────────────────────


class ModelDefaultItem(BaseModel):
    case_name: str
    model_id: int | None
    model_code: str | None
    model_kind: str | None


@router.get("/model-defaults", response_model=Result[list[ModelDefaultItem]])
async def list_model_defaults(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:read")),
) -> Result[list[ModelDefaultItem]]:
    rows = (await session.execute(select(ModelDefault))).scalars().all()
    out: list[ModelDefaultItem] = []
    for d in rows:
        code: str | None = None
        kind: str | None = None
        if d.model_id is not None:
            m = (
                await session.execute(
                    select(LLMModel).where(LLMModel.id == d.model_id)
                )
            ).scalar_one_or_none()
            if m is not None:
                code = m.code
                kind = m.kind
        out.append(
            ModelDefaultItem(
                case_name=d.case_name,
                model_id=d.model_id,
                model_code=code,
                model_kind=kind,
            )
        )
    return Result.ok(out)


class UpdateModelDefaultRequest(BaseModel):
    model_id: int | None = None


@router.post(
    "/model-defaults/{case_name}/update", response_model=Result[ModelDefaultItem]
)
async def update_model_default(
    case_name: str,
    req: UpdateModelDefaultRequest = Body(default_factory=UpdateModelDefaultRequest),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:write")),
) -> Result[ModelDefaultItem]:
    if case_name not in ("llm", "embedding", "vision"):
        raise ValidationError(message=f"未知 case_name: {case_name}")
    model_code: str | None = None
    model_kind: str | None = None
    if req.model_id is not None:
        m = (
            await session.execute(
                select(LLMModel).where(LLMModel.id == req.model_id)
            )
        ).scalar_one_or_none()
        if m is None:
            raise BusinessError(
                ResultCode.AgentNotFound, message=f"model 不存在: {req.model_id}"
            )
        model_code = m.code
        model_kind = m.kind

    existing = (
        await session.execute(
            select(ModelDefault).where(ModelDefault.case_name == case_name)
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(ModelDefault(case_name=case_name, model_id=req.model_id))
    else:
        existing.model_id = req.model_id
    await session.commit()
    logger.info("model_default updated: {} = {}", case_name, req.model_id)
    return Result.ok(
        ModelDefaultItem(
            case_name=case_name,
            model_id=req.model_id,
            model_code=model_code,
            model_kind=model_kind,
        )
    )
