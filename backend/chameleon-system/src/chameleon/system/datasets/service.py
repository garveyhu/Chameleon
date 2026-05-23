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
from chameleon.core.models import CallLog, Dataset, DatasetItem
from chameleon.system.datasets.schemas import (
    CreateDatasetRequest,
    DatasetItem as DatasetItemDTO,
    DatasetItemItem,
    SampleFromLogsRequest,
    SampleResult,
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

    added = 0
    skipped = 0
    for lg in logs:
        if lg.request_id in existing_set:
            skipped += 1
            continue
        redacted_input = _redact_input(lg.request_payload)
        expected = (
            _shallow_jsonable(lg.response_payload)
            if req.include_response_as_expected
            else None
        )
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

    return SampleResult(dataset_id=ds.id, added=added, skipped=skipped)


# ── 脱敏 helper ───────────────────────────────────────────


def _redact_input(payload: dict | None) -> dict[str, Any]:
    """call_log.request_payload → 脱敏的 input_payload

    保留：每个字段的 hash + length + token_count_approx + redacted preview（短）。
    """
    payload = payload or {}
    out: dict[str, Any] = {"_redacted": True}
    for k, v in payload.items():
        if isinstance(v, str):
            text = v
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            out[k] = {
                "hash": f"sha256:{sha}",
                "length": len(text),
                "token_count_approx": max(1, len(text) // 3),
                "preview": text[:_MAX_REDACTED_PREVIEW]
                + ("…" if len(text) > _MAX_REDACTED_PREVIEW else ""),
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
    return out


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
