"""api_key 业务服务

约束（规约）：
- 不返 ORM 给 API，必须转 ApiKeyItem
- 创建时返 plaintext（仅响应时），落库只存 hash + prefix
- 撤销 = 软撤（revoked_at = now），不真删
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.infra.auth import SCOPE_PREFIX, generate_api_key
from chameleon.core.models import ApiKey, CallLog
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)


def _slugify(name: str) -> str:
    """把 key 名归一化为 app_id 来源标签：小写 + 非字母数字转连字符。"""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "key"


async def create_api_key(
    session: AsyncSession,
    req: CreateApiKeyRequest,
    *,
    created_by_user_id: int | None = None,
) -> ApiKeyCreated:
    """创建一个 api_key，返 ApiKeyCreated（含明文，仅响应可见）

    单租户重构（块2）：key 不再挂 App 容器。app_id 是自由「调用方/来源标签」，
    请求未传则默认用 name 的 slug 兜底（仅作聚合/展示用，归属靠 api_key_id）。
    """
    # app_id 标签：请求显式传则用之，否则用 name 的 slug 兜底
    label = (req.app_id or "").strip() or _slugify(req.name)

    # 前缀按作用域域区分（global→chm_ / app→app- / kb→kbs-）
    prefix = SCOPE_PREFIX.get(req.scope_type, "chm_")
    plaintext, key_hash, key_prefix = generate_api_key(prefix)
    row = ApiKey(
        app_id=label,
        name=req.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        plain_key=plaintext,  # 留存明文，支持后续重复复制
        scopes=req.scopes,
        description=req.description,
        scope_type=req.scope_type,
        scope_ref=req.scope_ref,
        qpm_limit=req.qpm_limit,
        qpd_limit=req.qpd_limit,
        created_by_user_id=created_by_user_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    logger.info(
        "api_key created | app_id={} | scope={}:{} | by={}",
        row.app_id,
        row.scope_type,
        row.scope_ref,
        created_by_user_id,
    )
    return ApiKeyCreated.model_validate(row).model_copy(update={"plain_key": plaintext})


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
    # P22.1：model_code 用于查 price 算 cost；缺失则 cost=NULL
    # P23.C1 起 model_code 同时落库（cost dashboard 按模型聚合）
    model_code: str | None = None,
    # P23.C1 计费多维：user 落库（API-key 调用 user_id 可能为 NULL）
    user_id: int | None = None,
    # 会话账本：调用来源渠道（api/openai/embed/playground/internal）
    channel: str | None = None,
) -> None:
    """写一条 call_log（不阻塞响应——调用方可放 BackgroundTasks）

    P17.C1 起 call_log 同时承担"嵌套 observation"角色：
    - parent_id 指向同表父 request_id；NULL = trace 根
    - observation_type 区分 trace/span/generation/agent/tool/...

    parent_id 由调用方显式传入 —— 推荐用 chameleon.core.observe.observe()
    context manager 拿到 ObservationContext.parent_id 后传过来，明确且可测。
    """
    # P22.1：按当时生效价目算 cost（model_code 缺失 / 价目缺失则保持 NULL）
    cost_usd = None
    if model_code and (prompt_tokens or completion_tokens):
        try:
            from chameleon.system.pricing import calc_cost

            cost_usd = await calc_cost(
                session,
                model_code=model_code,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception:
            # cost 计算失败不阻塞 call_log 写入
            logger.exception(
                "cost calc failed | request_id={} | model={}",
                request_id,
                model_code,
            )

    log = CallLog(
        request_id=request_id,
        app_id=app_id,
        agent_key=agent_key,
        session_id=session_id,
        user_id=user_id,
        model_code=model_code,
        channel=channel,
        stream=stream,
        success=success,
        code=code,
        error_message=error_message,
        duration_ms=duration_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        spans=spans,
        request_payload=request_payload,
        response_payload=response_payload,
        parent_id=parent_id,
        observation_type=observation_type,
        completion_start_ms=completion_start_ms,
    )
    session.add(log)
    await session.flush()
