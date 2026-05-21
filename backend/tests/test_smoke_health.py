"""容器化部署冒烟测试

确保以下端点在 startup 后立即可用（CI 与 docker 健康检查都会跑）：
- GET /docs       FastAPI 自带 swagger（容器 health-check 用）
- GET /v1/system/info   非鉴权基础信息

不验业务功能（业务功能由 test_e2e_* 套件覆盖），只验"服务起来了"。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_docs_endpoint_available(client):
    """容器 healthcheck 依赖 /docs 200 OK"""
    resp = await client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()


@pytest.mark.asyncio
async def test_openapi_json_loads(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["info"]["title"]
    paths = body["paths"]
    assert "/v1/auth/login" in paths
    # 至少一个 admin endpoint 挂上了
    assert any(p.startswith("/v1/admin/") for p in paths)
    # embed widget 公开 API
    assert any("/v1/embed/" in p for p in paths)
