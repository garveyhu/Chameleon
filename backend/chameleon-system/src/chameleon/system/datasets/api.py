"""datasets HTTP 路由（/v1/admin/datasets）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.api.sse import sse_response
from chameleon.data.infra.db import get_session
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.datasets import ai_generate as ds_ai_generate
from chameleon.system.datasets import optimizer as ds_optimizer
from chameleon.system.datasets import runner as ds_runner
from chameleon.system.datasets import service as ds_service
from chameleon.aikit.tasks.eval.judges import list_judges
from chameleon.system.datasets.schemas import (
    AiGenStreamRequest,
    BatchDeleteItemsRequest,
    BatchDeleteItemsResult,
    BulkImportRequest,
    BulkImportResult,
    CategoryDef,
    ClassifyItemsResult,
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
    RefineCandidateRequest,
    RefinedCandidate,
    SampleFromLogsRequest,
    SamplePreviewResult,
    SampleResult,
    ScoreDistributionResult,
    SuggestCategoriesRequest,
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


@router.post("/categories/suggest", response_model=Result[list[CategoryDef]])
async def suggest_categories(
    req: SuggestCategoriesRequest,
    _: object = Depends(require_permission("datasets:write")),
) -> Result[list[CategoryDef]]:
    """AI 根据数据集用途（名/描述/系统提示词）建议一组能力维度（无状态，创建/编辑都用）。"""
    cats = await ds_ai_generate.suggest_categories(
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
    )
    return Result.ok([CategoryDef.model_validate(c) for c in cats])


@router.post(
    "/{dataset_id}/categories/classify",
    response_model=Result[ClassifyItemsResult],
)
async def classify_items(
    dataset_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[ClassifyItemsResult]:
    """AI 批量给未归类样本归类（一次 LLM 调用，最多 120 条）。"""
    updated = await ds_ai_generate.classify_items(session, dataset_id)
    return Result.ok(ClassifyItemsResult(updated=updated))


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
    "/{dataset_id}/sample-from-logs/preview",
    response_model=Result[SamplePreviewResult],
)
async def sample_from_logs_preview(
    dataset_id: int,
    req: SampleFromLogsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[SamplePreviewResult]:
    """采样预览：按 filter 收集候选返回评审（不落库），挑选/编辑后再 bulk-import。"""
    result = await ds_service.preview_sample_from_logs(session, dataset_id, req)
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


@router.post("/{dataset_id}/ai-generate/stream")
async def ai_generate_stream(
    dataset_id: int,
    req: AiGenStreamRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
):
    """流式 AI 扩样：种子 few-shot → LLM 流式产候选（走 eval 渠道，不落库）。

    SSE chunk：{"type":"delta"|"candidate"|"done","data":{...}}。选中候选由前端
    走 bulk-import 入库（生成与入库解耦，评审优先）。
    """
    return sse_response(
        ds_ai_generate.ai_generate_stream(
            session,
            dataset_id,
            task_description=req.task_description,
            count=req.count,
        ),
        log_label="datasets:ai-generate-stream",
    )


@router.post(
    "/{dataset_id}/ai-generate/refine",
    response_model=Result[RefinedCandidate],
)
async def ai_generate_refine(
    dataset_id: int,
    req: RefineCandidateRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[RefinedCandidate]:
    """单条 AI 优化 / 重新生成（非流式，走 eval 渠道，不落库）"""
    refined = await ds_ai_generate.refine_candidate(
        task_description=req.task_description,
        candidate=req.candidate.model_dump(),
        instruction=req.instruction,
        mode=req.mode,
    )
    return Result.ok(RefinedCandidate(**refined))


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
        api_key_id=req.api_key_id,
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


@router.get(
    "/{dataset_id}/runs/paged",
    response_model=Result[PageResult[DatasetRunRow]],
)
async def list_runs_paged(
    dataset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None),
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[PageResult[DatasetRunRow]]:
    result = await ds_service.list_runs_paged(
        session,
        dataset_id,
        PageParams(page=page, page_size=page_size),
        keyword=keyword,
        status=status,
    )
    return Result.ok(result)


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
