"""datasets 业务 service —— CRUD + 一键采样脱敏 + 人工标注

红线（plan §2 新增）：
- dataset_items.input_payload 不存原始 PII；采样时强制脱敏
  仅留 hash + length + token_count；展示用 redacted 替代字段
- include_response_as_expected=True 时 response 进 expected_output —— 这是 admin
  自愿"信任本次调用即金标准"的语义，由调用方明示开启
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import (
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
    CompareItemCell,
    CompareRunsResult,
    CreateDatasetRequest,
    DatasetItem as DatasetItemDTO,
    DatasetItemItem,
    DatasetRunDetail,
    DatasetRunItemRow,
    DatasetRunRow,
    MetricDistribution,
    SampleFromLogsRequest,
    SampleResult,
    ScoreBucket,
    ScoreDistributionResult,
    UpdateDatasetRequest,
    UpdateItemRequest,
)


_MAX_REDACTED_PREVIEW = 80  # 字符


async def list_datasets(session: AsyncSession) -> list[DatasetItemDTO]:
    rows = (
        (
            await session.execute(
                select(Dataset).order_by(Dataset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [DatasetItemDTO.model_validate(r) for r in rows]


async def get_dataset(session: AsyncSession, dataset_id: int) -> DatasetItemDTO:
    row = await _load_dataset(session, dataset_id)
    return DatasetItemDTO.model_validate(row)


async def create_dataset(
    session: AsyncSession, req: CreateDatasetRequest
) -> DatasetItemDTO:
    row = Dataset(name=req.name, description=req.description, item_count=0)
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
    session: AsyncSession, dataset_id: int, *, limit: int = 200
) -> list[DatasetItemItem]:
    await _load_dataset(session, dataset_id)  # 校验存在
    rows = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .order_by(DatasetItem.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [DatasetItemItem.model_validate(r) for r in rows]


async def update_item(
    session: AsyncSession, item_id: int, req: UpdateItemRequest
) -> DatasetItemItem:
    row = (
        await session.execute(
            select(DatasetItem).where(DatasetItem.id == item_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"dataset_item 不存在: {item_id}"
        )
    if req.expected_output is not None:
        row.expected_output = req.expected_output
    if req.meta is not None:
        row.meta = req.meta
    await session.flush()
    await session.refresh(row)
    item = DatasetItemItem.model_validate(row)
    await session.commit()
    return item


# ── 一键采样 ──────────────────────────────────────────────


async def sample_from_logs(
    session: AsyncSession,
    dataset_id: int,
    req: SampleFromLogsRequest,
) -> SampleResult:
    """按 filter 从 call_logs 批量采样 → dataset_items（脱敏）

    幂等：同一个 source_call_log_id 在同 dataset 内只 采一次。
    """
    ds = await _load_dataset(session, dataset_id)

    # 已采过的 source_call_log_id 集合（去重）
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

    added = 0
    skipped = 0
    dropped_pii = 0
    for lg in logs:
        if lg.request_id in existing_set:
            skipped += 1
            continue
        redacted_input, dropped_in = _redact_input(
            lg.request_payload, pii_strategy
        )
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
        item = DatasetItem(
            dataset_id=ds.id,
            source_call_log_id=lg.request_id,
            input_payload=redacted_input,
            expected_output=expected,
            meta={
                "agent_key": lg.agent_key,
                "app_id": lg.app_id,
                "success": lg.success,
                "duration_ms": lg.duration_ms,
                "pii_strategy": pii_strategy,
                "sampled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.add(item)
        added += 1
        existing_set.add(lg.request_id)

    ds.item_count = (
        await session.execute(
            select(func.count())
            .select_from(DatasetItem)
            .where(DatasetItem.dataset_id == ds.id)
        )
    ).scalar_one() + added - 0  # 上面尚未 commit，手算
    # 简化：让 commit 后 ORM 看到 added 行；先 flush 再 count
    await session.flush()
    ds.item_count = (
        await session.execute(
            select(func.count())
            .select_from(DatasetItem)
            .where(DatasetItem.dataset_id == ds.id)
        )
    ).scalar_one()
    await session.commit()

    return SampleResult(
        dataset_id=ds.id,
        added=added,
        skipped=skipped,
        dropped_pii=dropped_pii,
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
                **(raw.meta or {}),
                "source": "manual_import",
                "pii_strategy": pii_strategy,
                "imported_at": datetime.now(timezone.utc).isoformat(),
            },
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
    return BulkImportResult(
        dataset_id=ds.id, added=added, dropped_pii=dropped_pii
    )


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
            processed_preview, dropped = apply_pii_strategy(
                raw_preview, pii_strategy
            )
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


async def get_run(
    session: AsyncSession, run_id: int
) -> DatasetRunDetail:
    row = (
        await session.execute(
            select(DatasetRun).where(DatasetRun.id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"dataset_run 不存在: {run_id}"
        )
    return DatasetRunDetail.model_validate(row)


async def list_run_items(
    session: AsyncSession, run_id: int
) -> list[DatasetRunItemRow]:
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
    return [DatasetRunItemRow.model_validate(r) for r in rows]


async def compare_runs(
    session: AsyncSession, run_ids: list[int]
) -> CompareRunsResult:
    """item-by-item 对比 N 个 run

    同 dataset 内的 run 才能对比；否则 raise。
    """
    runs = (
        (
            await session.execute(
                select(DatasetRun).where(DatasetRun.id.in_(run_ids))
            )
        )
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
                select(DatasetRunItem).where(
                    DatasetRunItem.dataset_run_id.in_(run_ids)
                )
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
                cells=cells,
            )
        )

    return CompareRunsResult(
        runs=[DatasetRunRow.model_validate(r) for r in runs],
        rows=rows,
    )


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
        if not isinstance(scores, dict):
            continue
        for k, v in scores.items():
            if k.startswith("_") or k == "weighted_total":
                # _error 等内部字段不入分布；weighted_total 单独单独算
                pass
            if not isinstance(v, (int, float)):
                continue
            per_metric.setdefault(k, []).append((r.id, float(v)))

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


def _bucketize(
    values: list[float], n: int
) -> list[ScoreBucket]:
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
        await session.execute(
            select(Dataset).where(Dataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"dataset 不存在: {dataset_id}"
        )
    return row
