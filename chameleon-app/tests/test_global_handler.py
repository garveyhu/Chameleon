"""全局异常 handler + 响应封装集成测试"""

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from chameleon.app.main import create_app
from chameleon.core.api.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ResultCode,
)


def _build_test_app() -> FastAPI:
    """复用 create_app 但额外挂几条会抛异常的测试路由"""
    app = create_app()
    test_router = APIRouter(prefix="/test")

    class EchoIn(BaseModel):
        msg: str

    @test_router.get("/raise-not-found")
    async def raise_not_found() -> None:
        raise AgentNotFoundError(message="agent 'x' not registered")

    @test_router.get("/raise-business")
    async def raise_business() -> None:
        raise BusinessError(ResultCode.SessionIdInvalid)

    @test_router.get("/raise-unexpected")
    async def raise_unexpected() -> None:
        raise RuntimeError("boom")

    @test_router.post("/echo")
    async def echo(body: EchoIn) -> dict[str, str]:
        return {"msg": body.msg}

    app.include_router(test_router)
    return app


@pytest.fixture
async def client() -> AsyncClient:
    app = _build_test_app()
    # raise_app_exceptions=False：让全局 handler 接管，测试看到的是包装后响应
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert "X-Request-Id" in r.headers


async def test_ready(client: AsyncClient) -> None:
    r = await client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["pgvector"] is True


async def test_business_error_returns_404(client: AsyncClient) -> None:
    r = await client.get("/test/raise-not-found")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 40401
    assert body["message"] == "agent 'x' not registered"


async def test_business_error_session_invalid(client: AsyncClient) -> None:
    r = await client.get("/test/raise-business")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == 40010
    assert body["message"] == "session_id 非法"


async def test_unexpected_exception_returns_500(client: AsyncClient) -> None:
    r = await client.get("/test/raise-unexpected")
    assert r.status_code == 500
    body = r.json()
    assert body["success"] is False
    assert body["code"] == 50001
    # 不泄漏堆栈
    assert "boom" not in body["message"]


async def test_validation_error_returns_400(client: AsyncClient) -> None:
    r = await client.post("/test/echo", json={"wrong_key": "x"})
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == 40001
    assert "msg" in body["message"]  # 提到了字段名


async def test_request_id_echo_back(client: AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-Id": "req_test-123"})
    assert r.headers["X-Request-Id"] == "req_test-123"
