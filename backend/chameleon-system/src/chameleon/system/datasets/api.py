"""datasets HTTP 路由（/v1/admin/datasets）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.datasets import service as ds_service
from chameleon.system.datasets.schemas import (
    CreateDatasetRequest,
    DatasetDetail,
    DatasetItem,
    DatasetItemItem,
    SampleFromLogsRequest,
    SampleResult,
    UpdateDatasetRequest,
    UpdateItemRequest,
)

router = APIRouter(prefix="/v1/admin/datasets", tags=["admin:datasets"])


# ── Dataset CRUD ─────────────────────────────────────────


@router.get("", response_model=Result[list[DatasetItem]])
async def list_datasets(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[DatasetItem]]:
    items = await ds_service.list_datasets(session)
    return Result.ok(items)


@router.get("/{dataset_id}", response_model=Result[DatasetDetail])
async def get_dataset(
    dataset_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[DatasetDetail]:
    ds = await ds_service.get_dataset(session, dataset_id)
    return Result.ok(DatasetDetail.model_validate(ds.model_dump()))


@router.post("", response_model=Result[DatasetItem])
async def create_dataset(
    req: CreateDatasetRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItem]:
    item = await ds_service.create_dataset(session, req)
    return Result.ok(item)


@router.post("/{dataset_id}/update", response_model=Result[DatasetItem])
async def update_dataset(
    dataset_id: int,
    req: UpdateDatasetRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItem]:
    item = await ds_service.update_dataset(session, dataset_id, req)
    return Result.ok(item)


@router.post("/{dataset_id}/delete", response_model=Result[None])
async def delete_dataset(
    dataset_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[None]:
    await ds_service.delete_dataset(session, dataset_id)
    return Result.ok(None)


# ── Items ────────────────────────────────────────────────


@router.get(
    "/{dataset_id}/items", response_model=Result[list[DatasetItemItem]]
)
async def list_items(
    dataset_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[DatasetItemItem]]:
    items = await ds_service.list_items(session, dataset_id, limit=limit)
    return Result.ok(items)


@router.post(
    "/items/{item_id}/update", response_model=Result[DatasetItemItem]
)
async def update_item(
    item_id: int,
    req: UpdateItemRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItemItem]:
    item = await ds_service.update_item(session, item_id, req)
    return Result.ok(item)


# ── 一键采样 ──────────────────────────────────────────────


@router.post(
    "/{dataset_id}/sample-from-logs", response_model=Result[SampleResult]
)
async def sample_from_logs(
    dataset_id: int,
    req: SampleFromLogsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[SampleResult]:
    result = await ds_service.sample_from_logs(session, dataset_id, req)
    return Result.ok(result)
