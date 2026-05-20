import pytest
from sqlalchemy import text

from chameleon.core.db import AsyncSessionLocal, engine, get_session


async def test_engine_connect() -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_session_basic_query() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 42"))
        assert result.scalar() == 42


async def test_get_session_yields_usable_session() -> None:
    gen = get_session()
    session = await anext(gen)
    try:
        result = await session.execute(text("SELECT 'ok'"))
        assert result.scalar() == "ok"
    finally:
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
