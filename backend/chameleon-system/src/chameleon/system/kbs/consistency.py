"""KB 一致性扫描 + 修复 service —— P21.3 PR #65/#66

红线（plan §2 P21）：
- ⛔ scan 阶段只标 chunks.quarantined=True + 落 report.issues；不物理删
- ⛔ repair 阶段必须 admin 显式确认（API 端点单独存在）

扫描类型：
- orphan_chunk    —— chunk.doc_id 在 documents 不存在（FK CASCADE 防御性兜底）
- dim_mismatch    —— vector_dims(embedding) != kb.embedding_dim
- zero_vector     —— embedding 全 0（embedding service 失败留下的占位）

repair：物理删所有 quarantined=True 的 chunks（仅本 report 关联的 kb）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import (
    Chunk,
    Document,
    KbConsistencyReport,
    KnowledgeBase,
)

#: 单次扫描的 chunk 上限（防大 KB 撑爆 memory）
SCAN_BATCH_SIZE = 5000


async def scan_kb(
    session: AsyncSession, kb_id: int
) -> KbConsistencyReport:
    """对 KB 跑 3 类一致性扫描，标 quarantined + 落 report

    Returns:
        新建的 KbConsistencyReport
    """
    kb = (
        await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.NotFound, message=f"kb 不存在: {kb_id}"
        )

    report = KbConsistencyReport(
        kb_id=kb_id, status="running"
    )
    session.add(report)
    await session.flush()
    await session.refresh(report)
    report_id = report.id

    issues: list[dict[str, Any]] = []
    quarantined_ids: set[int] = set()

    try:
        # 1) orphan_chunk
        orphan_rows = (
            (
                await session.execute(
                    select(Chunk.id, Chunk.doc_id)
                    .where(Chunk.kb_id == kb_id)
                    .where(
                        ~select(Document.id)
                        .where(Document.id == Chunk.doc_id)
                        .exists()
                    )
                    .limit(SCAN_BATCH_SIZE)
                )
            )
            .all()
        )
        for cid, did in orphan_rows:
            issues.append(
                {
                    "type": "orphan_chunk",
                    "chunk_id": cid,
                    "kb_id": kb_id,
                    "reason": f"doc_id={did} 在 documents 表不存在",
                }
            )
            quarantined_ids.add(cid)

        # 2) dim_mismatch —— pg vector_dims() 函数
        # 注意：仅当 pgvector 提供该函数；否则跳过此检查
        try:
            dim_rows = (
                await session.execute(
                    text(
                        "SELECT id, vector_dims(embedding) AS d "
                        "FROM chunks WHERE kb_id = :kb_id "
                        "AND vector_dims(embedding) != :expected "
                        "LIMIT :lim"
                    ),
                    {"kb_id": kb_id, "expected": kb.embedding_dim, "lim": SCAN_BATCH_SIZE},
                )
            ).all()
            for cid, d in dim_rows:
                issues.append(
                    {
                        "type": "dim_mismatch",
                        "chunk_id": int(cid),
                        "kb_id": kb_id,
                        "reason": f"embedding dim={d} ≠ kb.dim={kb.embedding_dim}",
                    }
                )
                quarantined_ids.add(int(cid))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "dim_mismatch scan skipped (vector_dims unavailable?): {}", e
            )

        # 3) zero_vector —— embedding 各分量都为 0
        # pgvector 不直接支持 == zero array 比较；通过 norm 检查
        try:
            zero_rows = (
                await session.execute(
                    text(
                        "SELECT id FROM chunks "
                        "WHERE kb_id = :kb_id "
                        "AND (embedding <#> embedding) = 0 "
                        "LIMIT :lim"
                    ),
                    {"kb_id": kb_id, "lim": SCAN_BATCH_SIZE},
                )
            ).all()
            for (cid,) in zero_rows:
                issues.append(
                    {
                        "type": "zero_vector",
                        "chunk_id": int(cid),
                        "kb_id": kb_id,
                        "reason": "embedding 内积为 0（疑似 embedding 失败占位）",
                    }
                )
                quarantined_ids.add(int(cid))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "zero_vector scan skipped: {}", e
            )

        scanned_count = (
            await session.execute(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.kb_id == kb_id)
            )
        ).scalar_one()

        # 标 quarantined（按 reason 取每 chunk 的第一个 issue 类型）
        chunk_to_reason: dict[int, str] = {}
        for it in issues:
            cid = int(it["chunk_id"])
            if cid not in chunk_to_reason:
                chunk_to_reason[cid] = str(it["type"])
        for cid, reason_type in chunk_to_reason.items():
            await session.execute(
                update(Chunk)
                .where(Chunk.id == cid)
                .values(quarantined=True, quarantine_reason=reason_type)
            )

        report.issues = issues
        report.scanned_count = scanned_count
        report.quarantined_count = len(quarantined_ids)
        report.status = "done"
        report.finished_at = datetime.now(timezone.utc)
        await session.commit()

        logger.info(
            "kb consistency scan done | kb={} | report={} | scanned={} | quarantined={}",
            kb_id,
            report_id,
            scanned_count,
            len(quarantined_ids),
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("kb consistency scan failed | kb={}", kb_id)
        report.status = "failed"
        report.error_message = str(e)[:1024]
        report.finished_at = datetime.now(timezone.utc)
        await session.commit()
        raise

    await session.refresh(report)
    return report


async def list_reports(
    session: AsyncSession, kb_id: int, limit: int = 50
) -> list[KbConsistencyReport]:
    rows = (
        (
            await session.execute(
                select(KbConsistencyReport)
                .where(KbConsistencyReport.kb_id == kb_id)
                .order_by(KbConsistencyReport.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def get_report(
    session: AsyncSession, report_id: int
) -> KbConsistencyReport:
    row = (
        await session.execute(
            select(KbConsistencyReport).where(
                KbConsistencyReport.id == report_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"consistency report 不存在: {report_id}",
        )
    return row


async def repair_report(
    session: AsyncSession, report_id: int
) -> KbConsistencyReport:
    """物理删 KB 内所有 quarantined=True 的 chunks（红线：admin 显式触发）

    幂等：多次调返同 report；fixed_count 累计。
    只能在 status='done' 的报告上跑（避免在 running / pending 状态意外触发）。
    """
    report = await get_report(session, report_id)
    if report.status not in ("done", "fixed"):
        raise BusinessError(
            ResultCode.Fail,
            message=f"只能在 done/fixed 状态的报告上修复；当前 status={report.status}",
        )

    res = await session.execute(
        delete(Chunk).where(
            Chunk.kb_id == report.kb_id, Chunk.quarantined.is_(True)
        )
    )
    deleted = res.rowcount or 0
    report.fixed_count = (report.fixed_count or 0) + deleted
    report.status = "fixed"
    await session.commit()
    await session.refresh(report)
    logger.info(
        "kb consistency repair | report={} | deleted={}",
        report_id,
        deleted,
    )
    return report
