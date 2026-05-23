"""datasets HTTP 路由（/v1/admin/datasets）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.datasets import runner as ds_runner
from chameleon.system.datasets import service as ds_service
from chameleon.system.datasets.judges import list_judges
from chameleon.system.datasets.schemas import (
    BulkImportRequest,
    BulkImportResult,
    CompareRunsRequest,
    CompareRunsResult,
    CreateDatasetRequest,
    DatasetDetail,
    DatasetItem,
    DatasetItemItem,
    DatasetRunDetail,
    DatasetRunItemRow,
    DatasetRunRequest,
    DatasetRunRow,
    SampleFromLogsRequest,
    SampleResult,
    ScoreDistributionResult,
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


# 静态路径必须先于 /{dataset_id} 注册（FastAPI 按声明顺序匹配）
@router.get("/judges", response_model=Result[list[str]])
async def list_judges_endpoint(
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[str]]:
    return Result.ok(list_judges())


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


@router.post(
    "/{dataset_id}/items/bulk-import",
    response_model=Result[BulkImportResult],
)
async def bulk_import(
    dataset_id: int,
    req: BulkImportRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[BulkImportResult]:
    """手工 CSV/JSONL 前端解析后批量入 items（PII 策略可选）"""
    result = await ds_service.bulk_import_items(session, dataset_id, req)
    return Result.ok(result)


# ── DatasetRun（PR #25） ──────────────────────────────────


@router.post(
    "/{dataset_id}/run", response_model=Result[DatasetRunDetail]
)
async def run_dataset(
    dataset_id: int,
    req: DatasetRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetRunDetail]:
    """跑一次 dataset（持久化 + 写 scores）"""
    run = await ds_runner.run_dataset(
        session,
        dataset_id=dataset_id,
        name=req.name,
        model_override=req.model_override,
        prompt_override=req.prompt_override,
        judge=req.judge,
        eval_template_id=req.eval_template_id,
    )
    return Result.ok(DatasetRunDetail.model_validate(run))


@router.get(
    "/{dataset_id}/runs", response_model=Result[list[DatasetRunRow]]
)
async def list_runs(
    dataset_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[DatasetRunRow]]:
    items = await ds_service.list_runs(session, dataset_id)
    return Result.ok(items)


@router.get("/runs/{run_id}", response_model=Result[DatasetRunDetail])
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[DatasetRunDetail]:
    item = await ds_service.get_run(session, run_id)
    return Result.ok(item)


@router.get(
    "/runs/{run_id}/items",
    response_model=Result[list[DatasetRunItemRow]],
)
async def list_run_items(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[DatasetRunItemRow]]:
    items = await ds_service.list_run_items(session, run_id)
    return Result.ok(items)


@router.post("/runs/compare", response_model=Result[CompareRunsResult])
async def compare_runs(
    req: CompareRunsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[CompareRunsResult]:
    result = await ds_service.compare_runs(session, req.run_ids)
    return Result.ok(result)


@router.get(
    "/runs/{run_id}/score-distribution",
    response_model=Result[ScoreDistributionResult],
)
async def score_distribution(
    run_id: int,
    threshold: float = Query(default=0.5, ge=0.0, le=1.0),
    buckets: int = Query(default=10, ge=2, le=50),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[ScoreDistributionResult]:
    """P21.2：评分分布直方图 + 低分 item id 列表"""
    result = await ds_service.score_distribution(
        session, run_id, threshold=threshold, bucket_count=buckets
    )
    return Result.ok(result)
