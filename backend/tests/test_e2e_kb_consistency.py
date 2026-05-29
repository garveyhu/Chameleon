"""P21.3 PR #65/#66 E2E：KB 一致性扫描 + 修复"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import (
    Chunk,
    Document,
    KbConsistencyReport,
    KnowledgeBase,
    Role,
    User,
    UserRole,
)
from chameleon.data.utils.passwords import hash_password
from chameleon.system.seed.runner import run_seed_if_empty


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient):
    await run_seed_if_empty()
    rand = secrets.token_hex(3)
    username = f"e2e-kbc-{rand}"
    password = "TestPwd123!"
    async with AsyncSessionLocal() as s:
        role_id = (
            await s.execute(select(Role.id).where(Role.code == "admin"))
        ).scalar_one()
        u = User(
            username=username,
            password_hash=hash_password(password),
            status="active",
            must_change_password=False,
        )
        s.add(u)
        await s.flush()
        s.add(UserRole(user_id=u.id, role_id=role_id))
        await s.commit()
        uid = u.id
    r = await client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    yield r.json()["data"]["access_token"]
    async with AsyncSessionLocal() as s:
        await s.execute(delete(UserRole).where(UserRole.user_id == uid))
        await s.execute(delete(User).where(User.id == uid))
        await s.commit()


@pytest_asyncio.fixture
async def seeded_kb_with_issues():
    """造 1 KB + 1 doc + 3 chunks: 2 正常 + 1 zero_vector

    （orphan / dim_mismatch 在 PG 真实 schema 下无法绕过 FK + Vector 列约束
    手工造数据；scanner 防御性代码仍跑通，单测靠 zero_vector 案例覆盖标记 + 修复闭环）
    """
    async with AsyncSessionLocal() as s:
        rand = secrets.token_hex(3)
        kb = KnowledgeBase(
            kb_key=f"e2e-kbcons-{rand}",
            name="cons test",
            embedding_model="text-embedding-3-small",
            embedding_dim=1536,
        )
        s.add(kb)
        await s.flush()
        doc1 = Document(
            kb_id=kb.id,
            title="doc1",
            source_type="text",
            status="ready",
            chunk_count=3,
        )
        s.add(doc1)
        await s.flush()
        s.add_all(
            [
                Chunk(
                    doc_id=doc1.id,
                    kb_id=kb.id,
                    seq=0,
                    content="normal content 1",
                    embedding=[0.1] * 1536,
                ),
                Chunk(
                    doc_id=doc1.id,
                    kb_id=kb.id,
                    seq=1,
                    content="normal content 2",
                    embedding=[0.2] * 1536,
                ),
                # zero_vector chunk
                Chunk(
                    doc_id=doc1.id,
                    kb_id=kb.id,
                    seq=2,
                    content="zero embed",
                    embedding=[0.0] * 1536,
                ),
            ]
        )
        await s.commit()
        kb_id = kb.id

    yield {"kb_id": kb_id}

    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(KbConsistencyReport).where(
                KbConsistencyReport.kb_id == kb_id
            )
        )
        await s.execute(delete(Chunk).where(Chunk.kb_id == kb_id))
        await s.execute(delete(Document).where(Document.kb_id == kb_id))
        await s.execute(
            delete(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        await s.commit()


def _hdr(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


# ── scan ───────────────────────────────────────────────


async def test_scan_finds_zero_vector(
    client: AsyncClient,
    admin_token: str,
    seeded_kb_with_issues: dict,
):
    kb_id = seeded_kb_with_issues["kb_id"]
    r = await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"] == "done"
    assert data["scanned_count"] == 3
    assert data["quarantined_count"] >= 1
    types = {it["type"] for it in (data["issues"] or [])}
    # zero_vector 至少命中（依赖 pgvector inner product 检查）
    assert "zero_vector" in types


async def test_scan_marks_chunks_quarantined(
    seeded_kb_with_issues: dict,
):
    kb_id = seeded_kb_with_issues["kb_id"]
    async with AsyncSessionLocal() as s:
        from chameleon.system.kbs.consistency import scan_kb

        await scan_kb(s, kb_id)
        q_count = (
            await s.execute(
                select(Chunk).where(
                    Chunk.kb_id == kb_id, Chunk.quarantined.is_(True)
                )
            )
        ).scalars().all()
        assert len(q_count) >= 1
        for c in q_count:
            assert c.quarantine_reason in {
                "orphan_chunk",
                "dim_mismatch",
                "zero_vector",
            }


async def test_scan_unknown_kb_404(
    client: AsyncClient, admin_token: str
):
    r = await client.post(
        "/v1/admin/kbs/999999999/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    assert r.status_code in (400, 404, 500)


# ── list / get reports ────────────────────────────────


async def test_list_reports_returns_history(
    client: AsyncClient,
    admin_token: str,
    seeded_kb_with_issues: dict,
):
    kb_id = seeded_kb_with_issues["kb_id"]
    await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    lr = await client.get(
        f"/v1/admin/kbs/{kb_id}/consistency-reports",
        headers=_hdr(admin_token),
    )
    assert lr.status_code == 200
    assert len(lr.json()["data"]) >= 2


async def test_get_report_includes_issues(
    client: AsyncClient,
    admin_token: str,
    seeded_kb_with_issues: dict,
):
    kb_id = seeded_kb_with_issues["kb_id"]
    sr = await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    rid = sr.json()["data"]["id"]
    gr = await client.get(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/{rid}",
        headers=_hdr(admin_token),
    )
    assert gr.status_code == 200
    data = gr.json()["data"]
    assert data["id"] == rid
    assert isinstance(data["issues"], list)


# ── repair ─────────────────────────────────────────────


async def test_repair_deletes_quarantined_chunks(
    client: AsyncClient,
    admin_token: str,
    seeded_kb_with_issues: dict,
):
    """scan → repair → quarantined chunks 物理删；fixed_count 累计"""
    kb_id = seeded_kb_with_issues["kb_id"]
    sr = await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/scan",
        headers=_hdr(admin_token),
    )
    rid = sr.json()["data"]["id"]
    q_before = sr.json()["data"]["quarantined_count"]
    assert q_before >= 1

    rr = await client.post(
        f"/v1/admin/kbs/{kb_id}/consistency-reports/{rid}/repair",
        headers=_hdr(admin_token),
    )
    assert rr.status_code == 200, rr.text
    data = rr.json()["data"]
    assert data["status"] == "fixed"
    assert data["fixed_count"] == q_before

    # 验证：quarantined chunks 已被物理删
    async with AsyncSessionLocal() as s:
        remaining = (
            await s.execute(
                select(Chunk).where(
                    Chunk.kb_id == kb_id, Chunk.quarantined.is_(True)
                )
            )
        ).scalars().all()
        assert len(remaining) == 0


async def test_repair_only_done_status(
    seeded_kb_with_issues: dict,
):
    """non-done 报告不能 repair（防止意外触发）"""
    kb_id = seeded_kb_with_issues["kb_id"]
    async with AsyncSessionLocal() as s:
        from chameleon.core.api.exceptions import BusinessError
        from chameleon.system.kbs.consistency import repair_report
        pending = KbConsistencyReport(kb_id=kb_id, status="pending")
        s.add(pending)
        await s.commit()
        await s.refresh(pending)
        import pytest
        with pytest.raises(BusinessError):
            await repair_report(s, pending.id)
