"""Phase 5 端到端知识库冒烟

链路：admin/app key → 建 KB → ingest 文档 → 轮询 task → search → 验命中
"""

from __future__ import annotations

import asyncio

from httpx import AsyncClient


async def _wait_task(
    client: AsyncClient, app_key: str, task_id: int, timeout_sec: float = 5.0
) -> dict:
    """轮询 task 直到 success / failed"""
    headers = {"Authorization": f"Bearer {app_key}"}
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while True:
        r = await client.get(f"/v1/tasks/{task_id}", headers=headers)
        assert r.status_code == 200
        body = r.json()
        item = body["data"]
        if item["status"] in ("success", "failed"):
            return item
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"task {task_id} stuck at {item['status']}")
        await asyncio.sleep(0.05)


async def test_kb_crud_basic(client: AsyncClient, app_key: str) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}

    # create
    r = await client.post(
        "/v1/knowledge",
        headers=headers,
        json={"kb_key": "e2e-sales-docs", "name": "销售文档"},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["kb_key"] == "e2e-sales-docs"
    assert body["embedding_dim"] == 1536

    # list
    r = await client.get("/v1/knowledge", headers=headers)
    keys = {k["kb_key"] for k in r.json()["data"]["items"]}
    assert "e2e-sales-docs" in keys

    # update
    r = await client.post(
        "/v1/knowledge/e2e-sales-docs/update",
        headers=headers,
        json={"description": "公司销售相关全部文档"},
    )
    assert r.json()["data"]["description"] == "公司销售相关全部文档"

    # delete (soft)
    r = await client.post(
        "/v1/knowledge/e2e-sales-docs/delete",
        headers=headers,
    )
    assert r.status_code == 200

    # 软删后 list 不出现
    r = await client.get("/v1/knowledge", headers=headers)
    keys = {k["kb_key"] for k in r.json()["data"]["items"]}
    assert "e2e-sales-docs" not in keys


async def test_kb_duplicate_key_rejected(client: AsyncClient, app_key: str) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    body = {"kb_key": "e2e-dup", "name": "x"}

    r1 = await client.post("/v1/knowledge", headers=headers, json=body)
    assert r1.status_code == 200

    r2 = await client.post("/v1/knowledge", headers=headers, json=body)
    assert r2.status_code == 400
    assert r2.json()["code"] == 40001


async def test_kb_not_found(client: AsyncClient, app_key: str) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    r = await client.post(
        "/v1/knowledge/e2e-nonexistent/update",
        headers=headers,
        json={"name": "x"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == 40403


async def test_ingest_text_and_search(client: AsyncClient, app_key: str) -> None:
    """端到端：ingest 一段文本 → 轮询 → search 回原文片段"""
    headers = {"Authorization": f"Bearer {app_key}"}

    # 建 KB
    await client.post(
        "/v1/knowledge",
        headers=headers,
        json={
            "kb_key": "e2e-rag",
            "name": "RAG 测试",
            "chunk_size": 50,
            "chunk_overlap": 10,
        },
    )

    # ingest 一段中等长度文本
    content = (
        "Chameleon 是 links 的个人 AI 中枢。支持 LangGraph 本地编排、"
        "DIFY 与 FastGPT 远调。统一会话存 PostgreSQL。"
        "知识库走 pgvector + HNSW 索引。"
    )
    r = await client.post(
        "/v1/knowledge/e2e-rag/documents",
        headers=headers,
        json={
            "title": "Chameleon 简介",
            "source_type": "text",
            "content": content,
        },
    )
    assert r.status_code == 200, r.text
    task_id = r.json()["data"]["task_id"]
    document_id = r.json()["data"]["document_id"]

    # 轮询
    final = await _wait_task(client, app_key, task_id)
    assert final["status"] == "success", final
    assert final["result"]["chunks"] >= 1

    # 文档状态 ready
    r = await client.get("/v1/knowledge/e2e-rag/documents", headers=headers)
    docs = {d["id"]: d for d in r.json()["data"]["items"]}
    assert docs[document_id]["status"] == "ready"

    # search：query 用原文片段 → 必能命中（DeterministicHash 同文本同向量）
    r = await client.post(
        "/v1/knowledge/e2e-rag/search",
        headers=headers,
        json={"query": "知识库走 pgvector", "top_k": 3},
    )
    assert r.status_code == 200
    hits = r.json()["data"]
    assert len(hits) >= 1
    # 验证 score 排序
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


async def test_search_empty_kb_returns_no_hits(
    client: AsyncClient, app_key: str
) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    await client.post(
        "/v1/knowledge",
        headers=headers,
        json={"kb_key": "e2e-empty", "name": "空"},
    )
    r = await client.post(
        "/v1/knowledge/e2e-empty/search",
        headers=headers,
        json={"query": "anything"},
    )
    assert r.status_code == 200
    assert r.json()["data"] == []


async def test_search_nonexistent_kb_404(client: AsyncClient, app_key: str) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    r = await client.post(
        "/v1/knowledge/e2e-no-such/search",
        headers=headers,
        json={"query": "x"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == 40403


async def test_delete_document_removes_chunks(
    client: AsyncClient, app_key: str
) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    await client.post(
        "/v1/knowledge",
        headers=headers,
        json={"kb_key": "e2e-del", "name": "del-test", "chunk_size": 30},
    )
    r = await client.post(
        "/v1/knowledge/e2e-del/documents",
        headers=headers,
        json={
            "title": "deletable",
            "source_type": "text",
            "content": "唯一内容 unique-string-zzz",
        },
    )
    task_id = r.json()["data"]["task_id"]
    document_id = r.json()["data"]["document_id"]
    await _wait_task(client, app_key, task_id)

    # search 应能命中
    r = await client.post(
        "/v1/knowledge/e2e-del/search",
        headers=headers,
        json={"query": "唯一内容 unique-string-zzz"},
    )
    assert len(r.json()["data"]) >= 1

    # 删
    r = await client.post(
        f"/v1/knowledge/e2e-del/documents/{document_id}/delete",
        headers=headers,
    )
    assert r.status_code == 200

    # search 应空
    r = await client.post(
        "/v1/knowledge/e2e-del/search",
        headers=headers,
        json={"query": "唯一内容 unique-string-zzz"},
    )
    assert r.json()["data"] == []


async def test_in_process_search_kb(app_key: str) -> None:
    """from chameleon.integrations.knowledge import search_kb 可被 agent 用"""
    # 先建 KB 并 ingest（用 HTTP 方便，但 search 用 in-process）
    from httpx import ASGITransport
    from httpx import AsyncClient as Client

    from chameleon.app.main import create_app
    from chameleon.integrations.knowledge import search_kb

    app = create_app()
    async with Client(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        headers = {"Authorization": f"Bearer {app_key}"}
        await c.post(
            "/v1/knowledge",
            headers=headers,
            json={"kb_key": "e2e-inproc", "name": "in-process test", "chunk_size": 40},
        )
        r = await c.post(
            "/v1/knowledge/e2e-inproc/documents",
            headers=headers,
            json={
                "title": "x",
                "source_type": "text",
                "content": "in-process-search 验证文本",
            },
        )
        await _wait_task(c, app_key, r.json()["data"]["task_id"])

    # 直接调 in-process API
    hits = await search_kb(
        "e2e-inproc",
        "in-process-search 验证文本",
        top_k=2,
    )
    assert len(hits) >= 1
    assert hits[0].content


async def test_task_not_found(client: AsyncClient, app_key: str) -> None:
    headers = {"Authorization": f"Bearer {app_key}"}
    r = await client.get("/v1/tasks/999999999", headers=headers)
    assert r.status_code == 404
    assert r.json()["code"] == 40405
