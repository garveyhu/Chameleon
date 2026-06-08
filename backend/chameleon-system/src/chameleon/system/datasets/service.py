"""datasets 业务 service —— CRUD + 一键采样脱敏 + 人工标注

红线（plan §2 新增）：
- dataset_items.input_payload 不存原始 PII；采样时强制脱敏
  仅留 hash + length + token_count；展示用 redacted 替代字段
- include_response_as_expected=True 时 response 进 expected_output —— 这是 admin
  自愿"信任本次调用即金标准"的语义，由调用方明示开启
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.data.models import (
    CallLog,
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
)
from chameleon.system.datasets.pii import (
    PiiStrategy,
    apply_pii_strategy,
    apply_pii_strategy_dict,
)
from chameleon.system.datasets.schemas import (
    BulkImportRequest,
    BulkImportResult,
    CategoryDef,
    CompareAnalysisResult,
    CompareItemCell,
    CompareRunsResult,
    CreateDatasetRequest,
    CreateItemRequest,
    DatasetItemItem,
    DatasetRunDetail,
    DatasetRunItemDetail,
    DatasetRunItemRow,
    DatasetRunRow,
    MetricDistribution,
    SampleCandidate,
    SampleFromLogsRequest,
    SamplePreviewResult,
    SampleResult,
    ScoreBucket,
    ScoreDistributionResult,
    UpdateDatasetRequest,
    UpdateItemRequest,
)
from chameleon.system.datasets.schemas import (
    DatasetItem as DatasetItemDTO,
)

_MAX_REDACTED_PREVIEW = 80  # 字符

# sort_by 白名单：API 入参 → DB 列
_DATASET_SORT_COLUMNS = {
    "created_at": Dataset.created_at,
    "name": Dataset.name,
    "item_count": Dataset.item_count,
}
_DATASET_SORT_DEFAULT = "created_at"


async def list_datasets(
    session: AsyncSession,
    page: PageParams,
    *,
    keyword: str | None = None,
    sort_by: str = _DATASET_SORT_DEFAULT,
    order: str = "desc",
) -> PageResult[DatasetItemDTO]:
    """分页列出 datasets，并对【当前页这批】补 run_count / last_run_score 聚合。"""
    stmt = select(Dataset)
    if keyword:
        stmt = stmt.where(Dataset.name.ilike(f"%{keyword}%"))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    sort_col = _DATASET_SORT_COLUMNS.get(
        sort_by, _DATASET_SORT_COLUMNS[_DATASET_SORT_DEFAULT]
    )
    sort_col = sort_col.asc() if order == "asc" else sort_col.desc()
    rows = (
        (
            await session.execute(
                stmt.order_by(sort_col).offset(page.offset).limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    items = [DatasetItemDTO.model_validate(r) for r in rows]
    if not rows:
        return PageResult(
            items=items, total=total, page=page.page, page_size=page.page_size
        )

    ids = [r.id for r in rows]
    cnt_rows = (
        await session.execute(
            select(DatasetRun.dataset_id, func.count())
            .where(DatasetRun.dataset_id.in_(ids))
            .group_by(DatasetRun.dataset_id)
        )
    ).all()
    cnt_map = {did: n for did, n in cnt_rows}

    # 每个 dataset 最近一次运行的 summary.mean_score
    last_rows = (
        await session.execute(
            select(DatasetRun.dataset_id, DatasetRun.summary)
            .where(DatasetRun.dataset_id.in_(ids))
            .order_by(DatasetRun.dataset_id, DatasetRun.created_at.desc())
        )
    ).all()
    last_score_map: dict[int, float | None] = {}
    for did, summary in last_rows:
        if did not in last_score_map:  # desc 排序后首次见即最近
            last_score_map[did] = _extract_mean_score(summary)

    for it in items:
        it.run_count = cnt_map.get(it.id, 0)
        it.last_run_score = last_score_map.get(it.id)
    return PageResult(
        items=items, total=total, page=page.page, page_size=page.page_size
    )


def _extract_mean_score(summary: dict[str, Any] | None) -> float | None:
    if not summary:
        return None
    for k in ("mean_score", "mean", "avg_score"):
        v = summary.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


async def get_dataset(session: AsyncSession, dataset_id: int) -> DatasetItemDTO:
    row = await _load_dataset(session, dataset_id)
    return DatasetItemDTO.model_validate(row)


async def create_dataset(
    session: AsyncSession, req: CreateDatasetRequest
) -> DatasetItemDTO:
    row = Dataset(
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        categories=[c.model_dump() for c in req.categories]
        if req.categories
        else None,
        item_count=0,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = DatasetItemDTO.model_validate(row)
    await session.commit()
    return item


async def update_dataset(
    session: AsyncSession, dataset_id: int, req: UpdateDatasetRequest
) -> DatasetItemDTO:
    row = await _load_dataset(session, dataset_id)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.system_prompt is not None:
        row.system_prompt = req.system_prompt
    # categories：传了就覆盖（[] 清空），None 不动
    if req.categories is not None:
        row.categories = [c.model_dump() for c in req.categories]
    await session.flush()
    await session.refresh(row)
    item = DatasetItemDTO.model_validate(row)
    await session.commit()
    return item


async def delete_dataset(session: AsyncSession, dataset_id: int) -> None:
    row = await _load_dataset(session, dataset_id)
    await session.execute(delete(Dataset).where(Dataset.id == row.id))
    # items 走 ondelete=CASCADE
    await session.commit()


# ── items ────────────────────────────────────────────────


async def list_items(
    session: AsyncSession, dataset_id: int, page: PageParams
) -> PageResult[DatasetItemItem]:
    """分页列出某 dataset 的样本（按创建时间倒序）。

    注意：电子表格视图的动态列推断只能基于【当前页】这批样本的 input_payload
    顶层 key 并集；翻页可能出现新列。需要看全量列时调大 page_size。
    """
    await _load_dataset(session, dataset_id)  # 校验存在
    total = (
        await session.execute(
            select(func.count())
            .select_from(DatasetItem)
            .where(DatasetItem.dataset_id == dataset_id)
        )
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .order_by(DatasetItem.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    items = [DatasetItemItem.model_validate(r) for r in rows]
    return PageResult(
        items=items, total=total, page=page.page, page_size=page.page_size
    )


async def create_item(
    session: AsyncSession, dataset_id: int, req: CreateItemRequest
) -> DatasetItemItem:
    """电子表格单条新增样本（H2）

    与 bulk-import 一致：对 input_payload / expected_output 跑一次 PII 策略
    （默认 mask），落库后重算冗余 item_count。

    Raises:
        BusinessError: dataset 不存在，或 drop 策略下输入命中 PII 被整条丢弃。
    """
    ds = await _load_dataset(session, dataset_id)
    pii_strategy: PiiStrategy = req.pii_strategy  # type: ignore[assignment]
    masked_input, dropped_in = apply_pii_strategy_dict(req.input_payload, pii_strategy)
    masked_expected, dropped_out = apply_pii_strategy_dict(
        req.expected_output, pii_strategy
    )
    if dropped_in or dropped_out:
        raise BusinessError(
            ResultCode.Fail,
            message="输入或预期输出命中 PII，drop 策略下无法新增",
        )
    item = DatasetItem(
        dataset_id=ds.id,
        source_call_log_id=None,
        input_payload=masked_input or {},
        expected_output=masked_expected,
        meta={
            **(req.meta or {}),
            "source": "manual_add",
            "pii_strategy": pii_strategy,
            "added_at": datetime.now(timezone.utc).isoformat(),
        },
        note=(req.note or None),
        category=(req.category or None),
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    ds.item_count = await _count_items(session, ds.id)
    out = DatasetItemItem.model_validate(item)
    await session.commit()
    return out


async def delete_item(session: AsyncSession, item_id: int) -> None:
    """电子表格单条删除样本（H2）

    删除后回查 dataset_id 重算冗余 item_count，避免列表角标漂移。
    """
    row = (
        await session.execute(select(DatasetItem).where(DatasetItem.id == item_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"dataset_item 不存在: {item_id}")
    dataset_id = row.dataset_id
    await session.execute(delete(DatasetItem).where(DatasetItem.id == item_id))
    await session.flush()
    ds = (
        await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ).scalar_one_or_none()
    if ds is not None:
        ds.item_count = await _count_items(session, dataset_id)
    await session.commit()


async def batch_delete_items(
    session: AsyncSession, dataset_id: int, item_ids: list[int]
) -> int:
    """A2：批量删除某 dataset 下的多条样本，单次重算 item_count。

    只删属于该 dataset 的 item（防跨集越权删）；删完回算冗余 item_count。

    Returns:
        实际删除的样本数。
    """
    ds = await _load_dataset(session, dataset_id)
    result = await session.execute(
        delete(DatasetItem).where(
            DatasetItem.dataset_id == ds.id,
            DatasetItem.id.in_(item_ids),
        )
    )
    deleted = result.rowcount or 0
    await session.flush()
    ds.item_count = await _count_items(session, ds.id)
    await session.commit()
    return deleted


async def update_item(
    session: AsyncSession, item_id: int, req: UpdateItemRequest
) -> DatasetItemItem:
    row = (
        await session.execute(select(DatasetItem).where(DatasetItem.id == item_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"dataset_item 不存在: {item_id}")
    if req.input_payload is not None:
        row.input_payload = req.input_payload
    if req.expected_output is not None:
        row.expected_output = req.expected_output
    if req.meta is not None:
        row.meta = req.meta
    # note：传入即覆盖；空串 → 清空（None 表示「不动」，由前端按需带上）
    if req.note is not None:
        row.note = req.note or None
    if req.category is not None:
        row.category = req.category or None
    await session.flush()
    await session.refresh(row)
    item = DatasetItemItem.model_validate(row)
    await session.commit()
    return item


# ── 一键采样 ──────────────────────────────────────────────


async def _collect_sample_candidates(
    session: AsyncSession,
    ds: Dataset,
    req: SampleFromLogsRequest,
) -> tuple[list[dict[str, Any]], int, int]:
    """按 filter 从 call_logs 收集候选样本（脱敏），**不落库**。

    幂等：同 dataset 已采过的 source_call_log_id 跳过。
    返回 (candidates, skipped, dropped_pii)；candidate 含
    source_call_log_id / input_payload(脱敏) / expected_output / meta。
    sample_from_logs（直接导入）与 preview_sample_from_logs（评审预览）共用此收集逻辑，
    确保脱敏 / 去重 / 字段口径不分叉。
    """
    existing = (
        (
            await session.execute(
                select(DatasetItem.source_call_log_id).where(
                    DatasetItem.dataset_id == ds.id
                )
            )
        )
        .scalars()
        .all()
    )
    existing_set = {x for x in existing if x is not None}

    stmt = select(CallLog)
    if req.app_id is not None:
        stmt = stmt.where(CallLog.app_id == req.app_id)
    if req.agent_key is not None:
        stmt = stmt.where(CallLog.agent_key == req.agent_key)
    if req.success is not None:
        stmt = stmt.where(CallLog.success.is_(req.success))
    if req.since is not None:
        stmt = stmt.where(CallLog.created_at >= req.since)
    if req.until is not None:
        stmt = stmt.where(CallLog.created_at <= req.until)
    # 只采 trace 根（避免子 observation 重复）
    stmt = stmt.where(CallLog.parent_id.is_(None))
    stmt = stmt.order_by(CallLog.created_at.desc()).limit(req.limit)

    logs = (await session.execute(stmt)).scalars().all()
    pii_strategy: PiiStrategy = req.pii_strategy  # type: ignore[assignment]

    candidates: list[dict[str, Any]] = []
    skipped = 0
    dropped_pii = 0
    for lg in logs:
        if lg.request_id in existing_set:
            skipped += 1
            continue
        redacted_input, dropped_in = _redact_input(lg.request_payload, pii_strategy)
        if dropped_in:
            dropped_pii += 1
            continue
        if req.include_response_as_expected:
            expected, dropped_out = apply_pii_strategy_dict(
                _shallow_jsonable(lg.response_payload), pii_strategy
            )
            if dropped_out:
                dropped_pii += 1
                continue
        else:
            expected = None
        candidates.append(
            {
                "source_call_log_id": lg.request_id,
                "input_payload": redacted_input,
                "expected_output": expected,
                "meta": {
                    "agent_key": lg.agent_key,
                    "app_id": lg.app_id,
                    "success": lg.success,
                    "duration_ms": lg.duration_ms,
                    "pii_strategy": pii_strategy,
                    "sampled_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        )
        existing_set.add(lg.request_id)
    return candidates, skipped, dropped_pii


async def sample_from_logs(
    session: AsyncSession,
    dataset_id: int,
    req: SampleFromLogsRequest,
) -> SampleResult:
    """按 filter 从 call_logs 批量采样 → dataset_items（脱敏，直接入库）。

    幂等：同一个 source_call_log_id 在同 dataset 内只采一次。
    """
    ds = await _load_dataset(session, dataset_id)
    candidates, skipped, dropped_pii = await _collect_sample_candidates(session, ds, req)

    new_items: list[DatasetItem] = []
    for c in candidates:
        item = DatasetItem(
            dataset_id=ds.id,
            source_call_log_id=c["source_call_log_id"],
            input_payload=c["input_payload"],
            expected_output=c["expected_output"],
            meta=c["meta"],
        )
        session.add(item)
        new_items.append(item)

    # flush 后 ORM 已分配 id；据此回算 item_count 并收集本次新建 id（供撤销）
    await session.flush()
    ds.item_count = await _count_items(session, ds.id)
    created_item_ids = [it.id for it in new_items]
    await session.commit()

    return SampleResult(
        dataset_id=ds.id,
        added=len(new_items),
        skipped=skipped,
        dropped_pii=dropped_pii,
        created_item_ids=created_item_ids,
    )


def _value_text(v: Any) -> str | None:
    """单个值 → 可读文本：字符串直取；脱敏结构 {hash,length,preview,...} 取 preview。"""
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and isinstance(v.get("preview"), str):
        return v["preview"]
    return None


def _candidate_text(obj: dict[str, Any] | None, prefer: list[str]) -> str:
    """候选 input/expected 的 dict → 给评审卡片展示/编辑的纯文本。

    优先脱敏 preview / 字符串值；脱敏 mask 后字段是
    {_redacted: true, <field>: {hash,length,token_count_approx,preview}}，
    需取内层 preview 才可读，否则会把整坨脱敏 JSON 喂给用户。
    单字段直取；多字段优先 prefer 键；都不命中回退紧凑 JSON。
    """
    if not obj:
        return ""
    # 脱敏包装：{_redacted: true, <字段>: {...preview...}}
    if obj.get("_redacted"):
        for k, v in obj.items():
            if k == "_redacted":
                continue
            t = _value_text(v)
            if t is not None:
                return t
    keys = list(obj.keys())
    if len(keys) == 1:
        t = _value_text(obj[keys[0]])
        return t if t is not None else json.dumps(obj[keys[0]], ensure_ascii=False)
    for k in prefer:
        t = _value_text(obj.get(k))
        if t is not None:
            return t
    return json.dumps(obj, ensure_ascii=False)


async def preview_sample_from_logs(
    session: AsyncSession,
    dataset_id: int,
    req: SampleFromLogsRequest,
) -> SamplePreviewResult:
    """采样预览：按 filter 收集候选返回前端评审，**不落库**。

    用户在评审组件里挑选 / 编辑 / AI 优化后，再走 bulk-import 正式入库。
    """
    ds = await _load_dataset(session, dataset_id)
    candidates, skipped, dropped_pii = await _collect_sample_candidates(session, ds, req)
    out = [
        SampleCandidate(
            source_call_log_id=str(c["source_call_log_id"]),
            user_input=_candidate_text(
                c["input_payload"],
                ["user_input", "query", "question", "input", "text"],
            ),
            answer=_candidate_text(c["expected_output"], ["answer", "output", "value", "text"])
            or None,
            meta=c["meta"],
        )
        for c in candidates
    ]
    return SamplePreviewResult(
        candidates=out, skipped=skipped, dropped_pii=dropped_pii
    )


# ── 手工 import ──────────────────────────────────────────


async def bulk_import_items(
    session: AsyncSession,
    dataset_id: int,
    req: BulkImportRequest,
) -> BulkImportResult:
    """手工批量入 dataset_items（CSV/JSONL 前端解析后调用）

    PII 策略同采样：mask（默认）/ drop / keep。
    """
    ds = await _load_dataset(session, dataset_id)
    pii_strategy: PiiStrategy = req.pii_strategy  # type: ignore[assignment]
    added = 0
    dropped_pii = 0
    for raw in req.items:
        masked_input, dropped_in = apply_pii_strategy_dict(
            raw.input_payload, pii_strategy
        )
        if dropped_in:
            dropped_pii += 1
            continue
        masked_expected, dropped_out = apply_pii_strategy_dict(
            raw.expected_output, pii_strategy
        )
        if dropped_out:
            dropped_pii += 1
            continue
        item = DatasetItem(
            dataset_id=ds.id,
            source_call_log_id=None,
            input_payload=masked_input or {},
            expected_output=masked_expected,
            meta={
                # 尊重调用方显式来源（如 AI 扩样的 ai_generate），缺省才记手工导入。
                "source": (raw.meta or {}).get("source", "manual_import"),
                **(raw.meta or {}),
                "pii_strategy": pii_strategy,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            },
            note=(raw.note or None),
            category=(raw.category or None),
        )
        session.add(item)
        added += 1
    await session.flush()
    ds.item_count = (
        await session.execute(
            select(func.count())
            .select_from(DatasetItem)
            .where(DatasetItem.dataset_id == ds.id)
        )
    ).scalar_one()
    await session.commit()
    return BulkImportResult(dataset_id=ds.id, added=added, dropped_pii=dropped_pii)


# ── 脱敏 helper ───────────────────────────────────────────


def _redact_input(
    payload: dict | None, pii_strategy: PiiStrategy = "mask"
) -> tuple[dict[str, Any], bool]:
    """call_log.request_payload → 脱敏的 input_payload

    保留：每个字段的 hash + length + token_count_approx + redacted preview（短）。
    PII 策略（preview 字段）：
    - mask（默认）：preview 内 email / phone / id_card 替换占位符
    - drop：preview 含任意 PII → 整条 item 跳过（返 True）
    - keep：保留原文（仅 admin 明确无 PII 时）

    Returns:
        (redacted_input, should_drop)
    """
    payload = payload or {}
    out: dict[str, Any] = {"_redacted": True}
    for k, v in payload.items():
        if isinstance(v, str):
            text = v
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            raw_preview = text[:_MAX_REDACTED_PREVIEW] + (
                "…" if len(text) > _MAX_REDACTED_PREVIEW else ""
            )
            processed_preview, dropped = apply_pii_strategy(raw_preview, pii_strategy)
            if dropped:
                return out, True
            out[k] = {
                "hash": f"sha256:{sha}",
                "length": len(text),
                "token_count_approx": max(1, len(text) // 3),
                "preview": processed_preview,
            }
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, (list, dict)):
            sha = hashlib.sha256(repr(v).encode("utf-8")).hexdigest()[:16]
            out[k] = {
                "hash": f"sha256:{sha}",
                "shape": _structure_summary(v),
            }
        else:
            out[k] = {"type": type(v).__name__}
    return out, False


def _structure_summary(v: Any) -> dict[str, Any]:
    if isinstance(v, list):
        return {"kind": "list", "len": len(v)}
    if isinstance(v, dict):
        return {"kind": "dict", "keys": list(v.keys())[:10]}
    return {"kind": type(v).__name__}


def _shallow_jsonable(v: Any) -> dict[str, Any] | None:
    """expected_output 不脱敏（admin 信任本次调用为金标准）但确保是 dict"""
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    return {"value": v}


# ── DatasetRun list / detail / compare ───────────────────


async def list_runs(
    session: AsyncSession, dataset_id: int, limit: int = 50
) -> list[DatasetRunRow]:
    await _load_dataset(session, dataset_id)
    rows = (
        (
            await session.execute(
                select(DatasetRun)
                .where(DatasetRun.dataset_id == dataset_id)
                .order_by(DatasetRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [DatasetRunRow.model_validate(r) for r in rows]


async def list_runs_paged(
    session: AsyncSession,
    dataset_id: int,
    page: PageParams,
    keyword: str | None = None,
    status: str | None = None,
) -> PageResult[DatasetRunRow]:
    """运行列表分页 + 按名称/状态过滤；运行 tab 表格据此渲染。"""
    await _load_dataset(session, dataset_id)
    stmt = select(DatasetRun).where(DatasetRun.dataset_id == dataset_id)
    if keyword:
        stmt = stmt.where(DatasetRun.name.ilike(f"%{keyword}%"))
    if status:
        stmt = stmt.where(DatasetRun.status == status)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(DatasetRun.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=[DatasetRunRow.model_validate(r) for r in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def get_run(session: AsyncSession, run_id: int) -> DatasetRunDetail:
    row = (
        await session.execute(select(DatasetRun).where(DatasetRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"dataset_run 不存在: {run_id}")
    return DatasetRunDetail.model_validate(row)


async def list_run_items(
    session: AsyncSession, run_id: int
) -> list[DatasetRunItemDetail]:
    """逐样本明细，join dataset_item 带回 输入预览 / 完整输入 / 预期输出。

    模块 E 运行详情抽屉据此渲染样本明细表 + 三栏对比，前端无需再拉全样本。
    """
    rows = (
        (
            await session.execute(
                select(DatasetRunItem)
                .where(DatasetRunItem.dataset_run_id == run_id)
                .order_by(DatasetRunItem.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    item_ids = {r.dataset_item_id for r in rows}
    items_by_id: dict[int, DatasetItem] = {}
    if item_ids:
        items = (
            (
                await session.execute(
                    select(DatasetItem).where(DatasetItem.id.in_(item_ids))
                )
            )
            .scalars()
            .all()
        )
        items_by_id = {it.id: it for it in items}

    details: list[DatasetRunItemDetail] = []
    for r in rows:
        detail = DatasetRunItemDetail.model_validate(r)
        item = items_by_id.get(r.dataset_item_id)
        if item is not None:
            detail.input_preview = _extract_preview(item.input_payload)
            detail.input_payload = item.input_payload
            detail.expected_output = item.expected_output
        details.append(detail)
    return details


async def compare_runs(session: AsyncSession, run_ids: list[int]) -> CompareRunsResult:
    """item-by-item 对比 N 个 run

    同 dataset 内的 run 才能对比；否则 raise。
    """
    runs = (
        (await session.execute(select(DatasetRun).where(DatasetRun.id.in_(run_ids))))
        .scalars()
        .all()
    )
    if len(runs) != len(run_ids):
        missing = set(run_ids) - {r.id for r in runs}
        raise BusinessError(
            ResultCode.Fail, message=f"以下 run_ids 不存在: {sorted(missing)}"
        )
    dataset_ids = {r.dataset_id for r in runs}
    if len(dataset_ids) > 1:
        raise BusinessError(
            ResultCode.Fail,
            message="只能对比同 dataset 下的 runs",
        )
    dataset_id = next(iter(dataset_ids))

    items = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .order_by(DatasetItem.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    run_items = (
        (
            await session.execute(
                select(DatasetRunItem).where(DatasetRunItem.dataset_run_id.in_(run_ids))
            )
        )
        .scalars()
        .all()
    )
    # 按 (item_id, run_id) 索引
    by_item_run: dict[tuple[int, int], DatasetRunItem] = {
        (ri.dataset_item_id, ri.dataset_run_id): ri for ri in run_items
    }

    rows: list[CompareItemCell] = []
    for item in items:
        preview = _extract_preview(item.input_payload)
        cells: dict[int, DatasetRunItemRow] = {}
        for run_id in run_ids:
            ri = by_item_run.get((item.id, run_id))
            if ri is not None:
                cells[run_id] = DatasetRunItemRow.model_validate(ri)
        rows.append(
            CompareItemCell(
                dataset_item_id=item.id,
                input_preview=preview,
                expected_output=item.expected_output,
                note=item.note,
                category=item.category,
                cells=cells,
            )
        )

    ds = await _load_dataset(session, dataset_id)
    categories = (
        [CategoryDef.model_validate(c) for c in ds.categories]
        if ds.categories
        else None
    )
    return CompareRunsResult(
        runs=[DatasetRunRow.model_validate(r) for r in runs],
        rows=rows,
        categories=categories,
    )


def _cell_text(payload: Any) -> str:
    """从 {answer/sql/output/...} 或 dict 取可读文本（对比/分析展示用）。"""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        for k in ("answer", "sql", "output", "text", "content", "value"):
            v = payload.get(k)
            if isinstance(v, str):
                return v
        return json.dumps(payload, ensure_ascii=False)
    return str(payload)


def _to5(score: float | None) -> str:
    """归一 [0,1] → 1-5 档展示（None→'-'）。"""
    return "-" if score is None else f"{round(score * 4 + 1)}"


def _build_compare_digest(ds_name: str, result: CompareRunsResult) -> str:
    """把对比结果压成喂给 LLM 的紧凑文摘：模型概览 + 逐题得分表 + 分歧题实际 SQL。"""
    runs = result.runs
    rows = result.rows
    n = len(rows)

    def mean_of(run: DatasetRunRow) -> float | None:
        s = run.summary or {}
        v = s.get("mean_score") if isinstance(s, dict) else None
        return v if isinstance(v, (int, float)) else None

    # 模型概览（均分 + 5 档分布）
    lines: list[str] = [f"数据集：{ds_name}（{n} 题，满分按 1-5 档）", "", "参评模型："]
    ordered = sorted(runs, key=lambda r: (mean_of(r) or 0), reverse=True)
    for run in ordered:
        rid = run.id
        dist = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for row in rows:
            cell = row.cells.get(rid)
            sc = cell.score if cell else None
            if sc is None:
                continue
            dist[round(sc * 4 + 1)] += 1
        m = mean_of(run)
        m5 = f"{m * 4 + 1:.2f}" if m is not None else "-"
        lines.append(
            f"- {run.name}：均分 {m5}/5 ｜ 优{dist[5]} 良{dist[4]} 中{dist[3]} 差{dist[2]} 劣{dist[1]}"
        )

    # 逐题得分表
    lines += ["", "逐题得分（数字为 1-5 档；考察点即样本备注）："]
    header = "# | 考察点 | " + " | ".join(r.name for r in runs)
    lines.append(header)
    divergence: list[tuple[float, CompareItemCell]] = []
    for i, row in enumerate(rows, 1):
        scs = [row.cells.get(r.id).score if row.cells.get(r.id) else None for r in runs]
        nums = [s for s in scs if s is not None]
        spread = (max(nums) - min(nums)) if len(nums) >= 2 else 0.0
        divergence.append((spread, row))
        note = (row.note or "—")[:20]
        lines.append(
            f"{i} | {note} | " + " | ".join(_to5(s) for s in scs)
        )

    # 分歧最大的题：附各模型实际 SQL（最多 6 题，给 AI 引用具体例子）
    top = [r for sp, r in sorted(divergence, key=lambda x: x[0], reverse=True) if sp > 0][:6]
    if top:
        lines += ["", "分歧最大的题（附预期与各模型实际 SQL）："]
        for row in top:
            lines.append(f"\n【问题】{row.input_preview or ''}（考察点：{row.note or '—'}）")
            lines.append(f"  预期：{_cell_text(row.expected_output)[:200]}")
            for run in runs:
                cell = row.cells.get(run.id)
                if cell is None:
                    continue
                lines.append(
                    f"  {run.name}（{_to5(cell.score)}分）：{_cell_text(cell.actual_output)[:200]}"
                )
    return "\n".join(lines)


async def analyze_comparison(
    session: AsyncSession, run_ids: list[int]
) -> CompareAnalysisResult:
    """对 N 个运行的对比结果做 AI 总结分析（走 aikit，返回 markdown）。"""
    from chameleon.aikit import LLMRunner
    from chameleon.aikit.tasks.eval.compare import COMPARE_SYSTEM_PROMPT

    result = await compare_runs(session, run_ids)
    ds = await _load_dataset(session, result.runs[0].dataset_id)
    digest = _build_compare_digest(ds.name, result)
    analysis = await LLMRunner.run_text(
        digest,
        system=COMPARE_SYSTEM_PROMPT,
        channel="internal",
        retries=1,
        fallback="（分析生成失败，请稍后重试）",
    )
    return CompareAnalysisResult(analysis=analysis.strip())


def _extract_preview(input_payload: dict) -> str | None:
    """从脱敏 input_payload 取一段 preview 用于对比表格展示"""
    if not isinstance(input_payload, dict):
        return None
    for k in ("user_input", "query", "question", "input", "text"):
        v = input_payload.get(k)
        if isinstance(v, dict) and isinstance(v.get("preview"), str):
            return v["preview"]
        if isinstance(v, str):
            return v[:80]
    return None


# ── P21.2 评分分布 ────────────────────────────────────────


async def score_distribution(
    session: AsyncSession,
    run_id: int,
    *,
    threshold: float = 0.5,
    bucket_count: int = 10,
) -> ScoreDistributionResult:
    """聚合 dataset_run_items.eval_scores → 直方图 + 低分 item id 列表

    bucket：[0, 0.1), [0.1, 0.2), ..., [0.9, 1.0]（最后一桶闭区间）
    """
    rows = (
        (
            await session.execute(
                select(DatasetRunItem)
                .where(DatasetRunItem.dataset_run_id == run_id)
                .order_by(DatasetRunItem.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    per_metric: dict[str, list[tuple[int, float]]] = {}
    for r in rows:
        scores = r.eval_scores
        used_metric = False
        if isinstance(scores, dict):
            for k, v in scores.items():
                # _error 等内部字段、weighted_total 加权总分不入逐维度分布
                if k.startswith("_") or k == "weighted_total":
                    continue
                if not isinstance(v, (int, float)):
                    continue
                per_metric.setdefault(k, []).append((r.id, float(v)))
                used_metric = True
        # 兜底：无 eval_template 的纯 judge run（eval_scores 空）用 scalar score
        # 做「总分」单维度分布，否则直方图对最常见的 run 类型是空的
        if not used_metric and r.score is not None:
            per_metric.setdefault("总分", []).append((r.id, float(r.score)))

    metrics_out: list[MetricDistribution] = []
    total_scored = 0
    for metric_name, pairs in per_metric.items():
        total_scored = max(total_scored, len(pairs))
        scores_only = [s for _, s in pairs]
        mean_v = sum(scores_only) / len(scores_only) if scores_only else None
        buckets = _bucketize(scores_only, bucket_count)
        low_ids = [iid for iid, s in pairs if s < threshold]
        metrics_out.append(
            MetricDistribution(
                metric_name=metric_name,
                mean=mean_v,
                buckets=buckets,
                low_score_item_ids=low_ids,
            )
        )

    return ScoreDistributionResult(
        run_id=run_id,
        threshold=threshold,
        total_scored_items=total_scored,
        metrics=metrics_out,
    )


def _bucketize(values: list[float], n: int) -> list[ScoreBucket]:
    """把 [0,1] 范围切 n 桶；最后一桶闭区间"""
    if n < 1:
        n = 10
    width = 1.0 / n
    counts = [0] * n
    for v in values:
        v = max(0.0, min(1.0, v))
        idx = int(v / width)
        if idx >= n:
            idx = n - 1
        counts[idx] += 1
    return [
        ScoreBucket(
            low=round(i * width, 4),
            high=round((i + 1) * width, 4),
            count=counts[i],
        )
        for i in range(n)
    ]


# ── helpers ───────────────────────────────────────────────


async def _load_dataset(session: AsyncSession, dataset_id: int) -> Dataset:
    row = (
        await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"dataset 不存在: {dataset_id}")
    return row


async def _count_items(session: AsyncSession, dataset_id: int) -> int:
    """重算某 dataset 当前 item 数（维护冗余 item_count 用）"""
    return (
        await session.execute(
            select(func.count())
            .select_from(DatasetItem)
            .where(DatasetItem.dataset_id == dataset_id)
        )
    ).scalar_one()
