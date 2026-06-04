"""datasets HTTP 路由（/v1/admin/datasets）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.db import get_session
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.datasets import ai_generate as ds_ai_generate
from chameleon.system.datasets import optimizer as ds_optimizer
from chameleon.system.datasets import runner as ds_runner
from chameleon.system.datasets import service as ds_service
from chameleon.system.datasets.judges import list_judges
from chameleon.system.datasets.schemas import (
    AiGenerateRequest,
    AiGenerateResult,
    BatchDeleteItemsRequest,
    BatchDeleteItemsResult,
    BulkImportRequest,
    BulkImportResult,
    CompareRunsRequest,
    CompareRunsResult,
    CreateDatasetRequest,
    CreateItemRequest,
    DatasetDetail,
    DatasetItem,
    DatasetItemItem,
    DatasetRunDetail,
    DatasetRunItemDetail,
    DatasetRunRequest,
    DatasetRunRow,
    OptimizeResult,
    SampleFromLogsRequest,
    SampleResult,
    ScoreDistributionResult,
    UpdateDatasetRequest,
    UpdateItemRequest,
)

router = APIRouter(prefix="/v1/admin/datasets", tags=["admin:datasets"])


# ── Dataset CRUD ─────────────────────────────────────────


@router.get("", response_model=Result[PageResult[DatasetItem]])
async def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[PageResult[DatasetItem]]:
    result = await ds_service.list_datasets(
        session,
        PageParams(page=page, page_size=page_size),
        keyword=keyword,
        sort_by=sort_by,
        order=order,
    )
    return Result.ok(result)


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
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItem]:
    item = await ds_service.create_dataset(session, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="dataset.create",
        resource_type="dataset",
        resource_id=item.id,
        after={"name": item.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{dataset_id}/update", response_model=Result[DatasetItem])
async def update_dataset(
    dataset_id: int,
    req: UpdateDatasetRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItem]:
    item = await ds_service.update_dataset(session, dataset_id, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="dataset.update",
        resource_type="dataset",
        resource_id=item.id,
        after={"name": item.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{dataset_id}/delete", response_model=Result[None])
async def delete_dataset(
    dataset_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[None]:
    await ds_service.delete_dataset(session, dataset_id)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="dataset.delete",
        resource_type="dataset",
        resource_id=dataset_id,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


# ── Items ────────────────────────────────────────────────


@router.get(
    "/{dataset_id}/items", response_model=Result[PageResult[DatasetItemItem]]
)
async def list_items(
    dataset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[PageResult[DatasetItemItem]]:
    result = await ds_service.list_items(
        session, dataset_id, PageParams(page=page, page_size=page_size)
    )
    return Result.ok(result)


@router.post(
    "/{dataset_id}/items/create", response_model=Result[DatasetItemItem]
)
async def create_item(
    dataset_id: int,
    req: CreateItemRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItemItem]:
    """H2 电子表格「+新增行」：单条样本入库 + 维护 item_count"""
    item = await ds_service.create_item(session, dataset_id, req)
    return Result.ok(item)


@router.post("/items/{item_id}/update", response_model=Result[DatasetItemItem])
async def update_item(
    item_id: int,
    req: UpdateItemRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetItemItem]:
    item = await ds_service.update_item(session, item_id, req)
    return Result.ok(item)


@router.post("/items/{item_id}/delete", response_model=Result[None])
async def delete_item(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[None]:
    """H2 电子表格删行：删单条样本 + 维护 item_count"""
    await ds_service.delete_item(session, item_id)
    return Result.ok(None)


@router.post(
    "/{dataset_id}/items/batch-delete",
    response_model=Result[BatchDeleteItemsResult],
)
async def batch_delete_items(
    dataset_id: int,
    req: BatchDeleteItemsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[BatchDeleteItemsResult]:
    """A2：批量删除样本 + 单次重算 item_count（两视图删除已选 / A3 撤销采样共用）"""
    deleted = await ds_service.batch_delete_items(session, dataset_id, req.item_ids)
    return Result.ok(BatchDeleteItemsResult(deleted=deleted))


# ── 一键采样 ──────────────────────────────────────────────


@router.post("/{dataset_id}/sample-from-logs", response_model=Result[SampleResult])
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


@router.post(
    "/{dataset_id}/ai-generate",
    response_model=Result[AiGenerateResult],
)
async def ai_generate(
    dataset_id: int,
    req: AiGenerateRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[AiGenerateResult]:
    """AI 扩样：种子样本 + 任务描述 → LLM 批量生成新样本入库（走 eval 渠道）"""
    added = await ds_ai_generate.ai_generate_items(
        session,
        dataset_id,
        task_description=req.task_description,
        count=req.count,
    )
    return Result.ok(AiGenerateResult(dataset_id=dataset_id, added=added))


# ── DatasetRun（PR #25） ──────────────────────────────────


@router.post("/{dataset_id}/run", response_model=Result[DatasetRunDetail])
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
        judge_config=req.judge_config,
        eval_template_id=req.eval_template_id,
        agent_key=req.agent_key,
    )
    return Result.ok(DatasetRunDetail.model_validate(run))


@router.get("/{dataset_id}/runs", response_model=Result[list[DatasetRunRow]])
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
    response_model=Result[list[DatasetRunItemDetail]],
)
async def list_run_items(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[DatasetRunItemDetail]]:
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


@router.post("/runs/{run_id}/optimize", response_model=Result[OptimizeResult])
async def optimize_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[OptimizeResult]:
    """H3：低分样本共性 → LLM 重写 Prompt + 优化报告（走 eval 渠道，产出落库）"""
    data = await ds_optimizer.optimize_run_prompt(session, run_id)
    return Result.ok(OptimizeResult(**data))


@router.post(
    "/runs/{run_id}/apply-optimized", response_model=Result[DatasetRunDetail]
)
async def apply_optimized_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[DatasetRunDetail]:
    """H3：用父 run 的优化 Prompt 重跑整个 dataset，落新子 run（版本链）"""
    new_run = await ds_optimizer.apply_optimized_run(session, run_id)
    return Result.ok(DatasetRunDetail.model_validate(new_run))
