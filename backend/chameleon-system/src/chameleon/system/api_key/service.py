"""api_key 业务服务

约束（规约）：
- 不返 ORM 给 API，必须转 ApiKeyItem
- 创建时返 plaintext（仅响应时），落库只存 hash + prefix
- 撤销 = 软撤（revoked_at = now），不真删
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.infra.auth import generate_api_key
from chameleon.core.models import ApiKey, App, CallLog
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)


async def create_api_key(
    session: AsyncSession,
    req: CreateApiKeyRequest,
    *,
    created_by_user_id: int | None = None,
) -> ApiKeyCreated:
    """创建一个 api_key，返 ApiKeyCreated（含明文，仅响应可见）

    v0.2 改造：移除 app_id 唯一校验（一 app 多 key 合法），FK 由 DB 强制 app 存在。

    过渡：app_id 对应的 App 不存在时自动创建一个（P6 完整 apps CRUD 上线后移除此 upsert）。
    """
    # 过渡 upsert：让现有 v0.1 用法（直接发 key 不先建 app）继续工作
    existing_app = (
        await session.execute(select(App.id).where(App.app_key == req.app_id))
    ).scalar_one_or_none()
    if existing_app is None:
        session.add(App(app_key=req.app_id, name=req.app_id))
        await session.flush()

    plaintext, key_hash, key_prefix = generate_api_key()
    row = ApiKey(
        app_id=req.app_id,
        name=req.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=req.scopes,
        description=req.description,
        created_by_user_id=created_by_user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    logger.info(
        "api_key created | app_id={} | scopes={} | by={}",
        row.app_id,
        row.scopes,
        created_by_user_id,
    )
    return ApiKeyCreated(
        id=row.id,
        app_id=row.app_id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=row.scopes,
        description=row.description,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        plain_key=plaintext,
    )


async def list_api_keys(
    session: AsyncSession,
    page: PageParams,
    *,
    include_revoked: bool = False,
) -> PageResult[ApiKeyItem]:
    stmt = select(ApiKey)
    if not include_revoked:
        stmt = stmt.where(ApiKey.revoked_at.is_(None))

    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                stmt.order_by(ApiKey.created_at.desc())
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )

    items = [ApiKeyItem.model_validate(r) for r in rows]
    return PageResult(
        items=items,
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


async def revoke_api_key(session: AsyncSession, key_id: int) -> ApiKeyItem:
    """软撤一个 key（revoked_at = now）"""
    row = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"api_key 不存在: {key_id}"
        )
    if row.revoked_at is not None:
        # 幂等：已撤再撤不报错
        return ApiKeyItem.model_validate(row)

    row.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)

    logger.info("api_key revoked | id={} | app_id={}", row.id, row.app_id)
    return ApiKeyItem.model_validate(row)


# ── call_log helpers（被 agent 模块使用） ─────────────────


async def record_call(
    session: AsyncSession,
    *,
    request_id: str,
    app_id: str,
    agent_key: str,
    session_id: str | None,
    stream: bool,
    success: bool,
    code: int,
    error_message: str | None,
    duration_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    spans: list[dict] | None = None,
    request_payload: dict | None = None,
    response_payload: dict | None = None,
    # P17.C1 嵌套 observation 字段
    parent_id: str | None = None,
    observation_type: str = "generation",
    completion_start_ms: int | None = None,
) -> None:
    """写一条 call_log（不阻塞响应——调用方可放 BackgroundTasks）

    P17.C1 起 call_log 同时承担"嵌套 observation"角色：
    - parent_id 指向同表父 request_id；NULL = trace 根
    - observation_type 区分 trace/span/generation/agent/tool/...

    parent_id 由调用方显式传入 —— 推荐用 chameleon.core.observe.observe()
    context manager 拿到 ObservationContext.parent_id 后传过来，明确且可测。
    """
    log = CallLog(
        request_id=request_id,
        app_id=app_id,
        agent_key=agent_key,
        session_id=session_id,
        stream=stream,
        success=success,
        code=code,
        error_message=error_message,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        spans=spans,
        request_payload=request_payload,
        response_payload=response_payload,
        parent_id=parent_id,
        observation_type=observation_type,
        completion_start_ms=completion_start_ms,
    )
    session.add(log)
    await session.flush()
