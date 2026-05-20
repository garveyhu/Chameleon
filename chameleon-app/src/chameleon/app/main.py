"""Chameleon FastAPI app 入口

Phase 0 最简版：仅 /health + /ready，不挂业务 router、不接 auth、不接 registry。
P1 集成 chameleon-core 的 config/logger/db/response/auth + 全局异常 handler。
P2 接入 providers registry 启动钩子。
P3+ 挂业务模块 router。
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# P0 直接读 config/.env；P1 切换 chameleon.core.config
_root = Path(__file__).resolve().parents[4]
_env_file = _root / "config" / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    raise RuntimeError("DATABASE_URL not set in config/.env")

# P0 简版 engine，无 pool 调优；P1 由 chameleon.core.db 接管
_engine = create_async_engine(_db_url, pool_pre_ping=True)

app = FastAPI(title="Chameleon", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, bool]:
    """基础存活探针（不查 DB）"""
    return {"ok": True}


@app.get("/ready")
async def ready() -> JSONResponse:
    """就绪探针：DB 可达 + vector 扩展可用"""
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            row = (
                await conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname='vector'")
                )
            ).first()
            vector_ok = row is not None
        return JSONResponse({"ok": True, "db": True, "pgvector": vector_ok})
    except Exception as e:
        # P1 全局 handler 接入后，这里改 raise BusinessError
        return JSONResponse(
            status_code=503,
            content={"ok": False, "db": False, "error": str(e)},
        )
