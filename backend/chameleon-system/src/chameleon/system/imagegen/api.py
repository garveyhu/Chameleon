"""imagegen HTTP 路由 (/v1/admin/imagegen)

暴露内置生图工作流清单，供「模型」表单在 kind=image 时选择工作流 + 渲染可调参数。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from chameleon.core.api.response import Result
from chameleon.integrations.mediagen import list_workflows
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


router = APIRouter(prefix="/v1/admin/imagegen", tags=["admin:imagegen"])


@router.get("/workflows", response_model=Result[list[WorkflowItem]])
async def list_image_workflows(
    _: object = Depends(require_permission("models:read")),
) -> Result[list[WorkflowItem]]:
    """列出内置生图工作流（id / name / 可调参数 spec）。"""
    return Result.ok([WorkflowItem(**wf) for wf in list_workflows()])
