"""Chameleon FastAPI app 入口

P1 完整版：接入 chameleon-core 的 logger / db / response / exceptions / auth。
全局异常 handler 接管 BusinessError / RequestValidationError / Exception。
X-Request-Id middleware：缺失则生成，回写响应头。
P2 接 providers registry 启动钩子；P3+ 挂业务模块 router。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text

from chameleon.core.db import engine
from chameleon.core.exceptions import (
    BusinessError,
    ResultCode,
    code_to_http_status,
)
from chameleon.core.logger import setup_logger
from chameleon.core.response import Result
from chameleon.providers.base import AGENTS, PROVIDERS, init_registry

REQUEST_ID_HEADER = "X-Request-Id"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """startup: 构建 registry + healthcheck warn-only；shutdown: 暂无清理"""
    init_registry()
    _log_registry_summary()
    await _trigger_healthchecks()
    yield


def create_app() -> FastAPI:
    setup_logger()

    app = FastAPI(title="Chameleon", version="0.1.0", lifespan=_lifespan)

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_health_routes(app)
    # P3+ 在这里挂业务 router

    logger.info("FastAPI app created")
    return app


def _log_registry_summary() -> None:
    """启动日志按设计文档 S2.5 末段格式化输出"""
    logger.info("─── Chameleon Registry ───")
    logger.info("Loaded {} providers: {}", len(PROVIDERS), ", ".join(PROVIDERS.keys()))
    logger.info("Loaded {} agents:", len(AGENTS))
    for key, agent in AGENTS.items():
        source = "(built-in)" if agent.provider == "langgraph" else "(from agents.yaml)"
        logger.info("  [{:<9}] {:<24} {}", agent.provider, key, source)


async def _trigger_healthchecks() -> None:
    """异步 ping 各 provider —— 失败仅 warn，不阻塞启动（裁决：warn-only）"""
    for name, provider in PROVIDERS.items():
        try:
            ok = await provider.healthcheck()
            if not ok:
                logger.warning("provider {} healthcheck returned False", name)
        except Exception as e:
            logger.warning("provider {} healthcheck failed: {}", name, e)


# ── Middleware ──────────────────────────────────────────


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[JSONResponse]],
    ) -> JSONResponse:
        req_id = (
            request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid.uuid4().hex[:24]}"
        )
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = req_id
        return response


# ── 全局异常 handler ────────────────────────────────────


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessError)
    async def handle_business_error(
        request: Request, exc: BusinessError
    ) -> JSONResponse:
        # message 是业务层精心准备的人话，可直接返
        return JSONResponse(
            status_code=code_to_http_status(int(exc.code)),
            content=Result.fail(exc.code, exc.message).model_dump(),
            headers={REQUEST_ID_HEADER: getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        msg = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(
            status_code=400,
            content=Result.fail(ResultCode.ValidationError, msg).model_dump(),
            headers={REQUEST_ID_HEADER: getattr(request.state, "request_id", "")},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception | path={}", request.url.path)
        # 兜底：不泄漏堆栈给客户端
        return JSONResponse(
            status_code=500,
            content=Result.fail(
                ResultCode.InternalError, ResultCode.InternalError.message
            ).model_dump(),
            headers={REQUEST_ID_HEADER: getattr(request.state, "request_id", "")},
        )


# ── 健康端点 ────────────────────────────────────────────


def _register_health_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/ready")
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                row = (
                    await conn.execute(
                        text("SELECT extname FROM pg_extension WHERE extname='vector'")
                    )
                ).first()
                vector_ok = row is not None
            return JSONResponse(
                Result.ok({"db": True, "pgvector": vector_ok}).model_dump()
            )
        except Exception as e:
            logger.exception("readyz failed")
            return JSONResponse(
                status_code=503,
                content=Result.fail(
                    ResultCode.DBError, f"db unreachable: {e}"
                ).model_dump(),
            )


# Module-level app instance（uvicorn 入口）
app = create_app()
