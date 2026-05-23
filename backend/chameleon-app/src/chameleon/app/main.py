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

from chameleon.api.agent import agents_router
from chameleon.api.embed import embed_router
from chameleon.system.admin import admin_router
from chameleon.system.agents import agents_admin_router
from chameleon.system.api_key import api_keys_router
from chameleon.system.apps import apps_router
from chameleon.system.abilities import abilities_router
from chameleon.system.audit_logs import audit_logs_router
from chameleon.system.auth import auth_router
from chameleon.system.channels import channels_router
from chameleon.system.dashboard import dashboard_router
from chameleon.system.datasets import datasets_router
from chameleon.system.eval_jobs import eval_jobs_router
from chameleon.system.eval_jobs import scheduler as eval_scheduler
from chameleon.system.embed_configs import embed_configs_router
from chameleon.system.graphs import graphs_router
from chameleon.system.tools import tools_router
from chameleon.system.kbs import kbs_admin_router
from chameleon.system.models import models_router
from chameleon.system.permissions import permissions_router
from chameleon.system.playground import playground_router
from chameleon.system.providers import providers_admin_router
from chameleon.system.roles import roles_router
from chameleon.system.schemas import schemas_router
from chameleon.system.scores import scores_router
from chameleon.system.search import search_router
from chameleon.system.settings import settings_router
from chameleon.system.users import users_router
from chameleon.api.conversation import conversations_router
from chameleon.api.knowledge import knowledge_router
from chameleon.api.task import tasks_router
from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    code_to_http_status,
)
from chameleon.core.api.response import Result
from chameleon.core.components.llms.factory import reload_llm_cache
from chameleon.core.infra import redis as redis_infra
from chameleon.core.infra.db import engine
from chameleon.core.infra.jwt import init_jwt
from chameleon.core.infra.logger import setup_logger
from chameleon.core.infra.object_store import get_object_store
from chameleon.core.utils.crypto import init_crypto
from chameleon.system.seed import run_seed_if_empty
from chameleon.providers.base import AGENTS, PROVIDERS, init_registry

REQUEST_ID_HEADER = "X-Request-Id"


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """startup: 加密 / JWT 初始化 → Redis ping → 构建 registry → healthcheck warn-only

    crypto init / jwt init：production 缺 key/secret fail-fast；dev 缺则 warn + demo
    Redis 不通 → fail-fast（JWT 黑名单 / 限流 / 配置缓存全靠它，缺则功能不可用）
    """
    init_crypto()
    init_jwt()

    await redis_infra.ping()
    logger.info("Redis connected")

    # MinIO bucket 自检（KB 文档原文走对象存储）
    try:
        get_object_store().ensure_bucket()
    except Exception:
        logger.warning("MinIO 不可用：KB 上传会失败（检查 docker compose / .env 凭据）")

    # DB 空 → seed 默认 admin / 角色 / 权限 / 模型 / agents（幂等）
    await run_seed_if_empty()

    # 从 DB 加载 LLM cache（业务热路径同步取）
    await reload_llm_cache()

    # 从 DB 加载 AGENTS / PROVIDERS dict
    await init_registry()
    _log_registry_summary()
    await _trigger_healthchecks()

    # eval_jobs scheduler 起 cron 触发器（DB 里 enabled=True 的 job 全部注册）
    await eval_scheduler.start()
    yield

    await eval_scheduler.shutdown()
    await redis_infra.aclose()


def create_app() -> FastAPI:
    setup_logger()

    app = FastAPI(title="Chameleon", version="0.1.0", lifespan=_lifespan)

    _register_middleware(app)
    _register_exception_handlers(app)
    _register_health_routes(app)
    _mount_routers(app)

    logger.info("FastAPI app created")
    return app


def _mount_routers(app: FastAPI) -> None:
    """挂载业务模块 router"""
    # 鉴权
    app.include_router(auth_router)
    # 管理后台
    app.include_router(api_keys_router)
    app.include_router(admin_router)
    app.include_router(settings_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(permissions_router)
    app.include_router(apps_router)
    app.include_router(providers_admin_router)
    app.include_router(channels_router)
    app.include_router(abilities_router)
    app.include_router(models_router)
    app.include_router(agents_admin_router)
    app.include_router(kbs_admin_router)
    app.include_router(dashboard_router)
    app.include_router(playground_router)
    app.include_router(audit_logs_router)
    app.include_router(embed_configs_router)
    app.include_router(graphs_router)
    app.include_router(tools_router)
    app.include_router(datasets_router)
    app.include_router(eval_jobs_router)
    app.include_router(search_router)
    app.include_router(schemas_router)
    app.include_router(scores_router)
    # 嵌入式业务
    app.include_router(embed_router)
    # 业务接口
    app.include_router(conversations_router)
    app.include_router(agents_router)
    app.include_router(knowledge_router)
    app.include_router(tasks_router)


def _log_registry_summary() -> None:
    """启动日志按设计文档 S2.5 末段格式化输出"""
    logger.info("─── Chameleon Registry ───")
    logger.info("Loaded {} providers: {}", len(PROVIDERS), ", ".join(PROVIDERS.keys()))
    logger.info("Loaded {} agents:", len(AGENTS))
    for key, agent in AGENTS.items():
        source = "(built-in)" if agent.provider == "local" else "(from agents.yaml)"
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
    from fastapi.middleware.cors import CORSMiddleware

    # CORS：admin / business API 默认仅同源；嵌入式路径 /v1/embed/*
    # 的跨域校验在 router 内动态做（按 embed_config.allowed_origins）。
    # 这里放开 /v1/embed/* 的 preflight，origin 白名单 router 内独立验。
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=False,  # embed 不带 cookie，避免 wildcard origin 冲突
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )

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
