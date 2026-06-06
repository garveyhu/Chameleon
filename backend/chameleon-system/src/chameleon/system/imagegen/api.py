"""mediagen HTTP 路由 (/v1/admin/imagegen)

暴露：
- 内置生图工作流清单（comfyui，供「模型」表单选工作流）
- 媒体模型的可调参数规约 + 风格预设（供生成面板动态渲染）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import ValidationError
from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.data.models import LLMModel, Provider
from chameleon.integrations.mediagen import (
    STYLE_PRESETS,
    MediaConfigError,
    build_media_target,
    build_param_spec,
    list_workflows,
)
from chameleon.system.auth.dependencies import require_permission


class WorkflowParam(BaseModel):
    key: str
    label: str
    type: str
    default: Any = None


class WorkflowItem(BaseModel):
    id: str
    name: str
    description: str
    params: list[WorkflowParam]


class ParamSpecOut(BaseModel):
    media_kind: str
    fields: list[dict[str, Any]]
    styles: list[dict[str, Any]]


router = APIRouter(prefix="/v1/admin/imagegen", tags=["admin:imagegen"])


@router.get("/workflows", response_model=Result[list[WorkflowItem]])
async def list_image_workflows(
    _: object = Depends(require_permission("models:read")),
) -> Result[list[WorkflowItem]]:
    """列出内置生图工作流（id / name / 可调参数 spec）。"""
    return Result.ok([WorkflowItem(**wf) for wf in list_workflows()])


@router.get("/param-spec", response_model=Result[ParamSpecOut])
async def get_param_spec(
    model_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
) -> Result[ParamSpecOut]:
    """按媒体模型 id 返回可调参数规约 + 风格预设，供生成面板动态渲染。"""
    model = await session.get(LLMModel, model_id)
    if model is None:
        raise ValidationError(message=f"模型不存在: {model_id}")
    provider = (
        await session.execute(select(Provider).where(Provider.id == model.provider_id))
    ).scalar_one_or_none()
    try:
        spec = build_param_spec(build_media_target(model, provider))
    except MediaConfigError:
        # 半配置：仍给风格预设 + 空字段，面板可用
        styles = STYLE_PRESETS if model.kind in ("image", "video") else []
        spec = {"media_kind": model.kind, "fields": [], "styles": styles}
    return Result.ok(ParamSpecOut(**spec))
