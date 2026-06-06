"""价目管理 HTTP 路由（/v1/admin/pricing）—— admin 价目 CRUD。

API 层零业务：鉴权 + 校验 + 调 service + 包 Result。价目按时间版本（改价新增
版本，不改老行），故「更新」语义即「新增当前生效版本」。币种统一 CNY。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.pricing import service

router = APIRouter(prefix="/v1/admin/pricing", tags=["admin:pricing"])


class SetTokenPricingRequest(BaseModel):
    model_code: str
    prompt_per_1k: float = Field(ge=0)
    completion_per_1k: float = Field(ge=0)


class SetMediaPricingRequest(BaseModel):
    model_code: str
    unit: str  # PricingUnit: image / video_second
    price: float = Field(ge=0)
    tier: str = ""  # video 分辨率档（720P/1080P）；image 留空


@router.get("/models", response_model=Result[list[dict]])
async def list_pricing(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
) -> Result[list[dict]]:
    """所有模型 + 当前生效价目。"""
    return Result.ok(await service.list_model_pricing(session))


@router.post("/token/update", response_model=Result[None])
async def update_token_pricing(
    req: SetTokenPricingRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[None]:
    """设 token 价目（新增时间版本）。"""
    await service.set_token_pricing(
        session,
        model_code=req.model_code,
        prompt_per_1k=req.prompt_per_1k,
        completion_per_1k=req.completion_per_1k,
    )
    return Result.ok(None)


@router.post("/media/update", response_model=Result[None])
async def update_media_pricing(
    req: SetMediaPricingRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[None]:
    """设媒体价目（按张 / 按秒 + 分辨率档，新增时间版本）。"""
    await service.set_media_pricing(
        session,
        model_code=req.model_code,
        unit=req.unit,
        price=req.price,
        tier=req.tier,
    )
    return Result.ok(None)
