"""SQLAlchemy 2.0 async engine + session 工厂

ORM 全栈 SQLAlchemy 2.0 async（声明式 + Mapped[]）；
禁用 SQLModel / Tortoise / raw SQL 业务持久层。
复杂查询用 SQLAlchemy Core / text() 在同一 session 里走。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from chameleon.core.config import inventory

# 不用 pool_pre_ping：async + asyncpg 下，pre_ping 的 do_ping 在断连重连路径偶发
# 落到非 greenlet 上下文 → MissingGreenlet（"首次写偶发失败、重试即成功"的根因）。
# 改用 pool_recycle 主动回收（短于常见 idle 超时）规避陈旧连接；真断连由 SQLAlchemy
# 的 connection invalidation 在下次 checkout 自愈。
engine = create_async_engine(
    inventory.database_url(),
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # commit 后 ORM 对象仍可读字段
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends：一个请求一个 session

    异常自动 rollback；正常退出 commit。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
