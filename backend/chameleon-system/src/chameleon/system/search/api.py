"""全站搜索 API (/v1/admin/search)

给 ⌘K 命令面板用：跨资源 ILIKE 模糊搜索，按 type 限制 + 总 limit。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.data.models import (
    Agent,
    EmbedConfig,
    KnowledgeBase,
    LLMModel,
    Provider,
    User,
)
from chameleon.system.auth.dependencies import require_permission

SearchType = Literal[
    "agent", "model", "provider", "kb", "user", "embed_config"
]


class SearchResult(BaseModel):
    type: SearchType
    id: int
    title: str
    snippet: str
    url: str
    icon: str  # lucide name


class SearchResponse(BaseModel):
    results: list[SearchResult]


router = APIRouter(prefix="/v1/admin/search", tags=["admin:search"])


def _truncate(s: str | None, n: int = 60) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + "..."


@router.get("", response_model=Result[SearchResponse])
async def search(
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("dashboard:read")),
) -> Result[SearchResponse]:
    """全站模糊搜索

    每类资源最多返 `limit/7 + 1` 条；按类型分组前端再筛选展示。
    """
    like = f"%{q}%"
    per = max(2, limit // 6)
    out: list[SearchResult] = []

    # agents
    agents = (
        (
            await session.execute(
                select(Agent)
                .where(
                    Agent.deleted_at.is_(None),
                    or_(
                        Agent.agent_key.ilike(like),
                        Agent.name.ilike(like),
                        Agent.description.ilike(like),
                    ),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for a in agents:
        out.append(
            SearchResult(
                type="agent",
                id=a.id,
                title=a.name or a.agent_key,
                snippet=_truncate(a.description or a.agent_key),
                url="/agents",
                icon="bot",
            )
        )

    # models
    models = (
        (
            await session.execute(
                select(LLMModel)
                .where(
                    LLMModel.deleted_at.is_(None),
                    LLMModel.code.ilike(like),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for m in models:
        out.append(
            SearchResult(
                type="model",
                id=m.id,
                title=m.code,
                snippet=f"kind={m.kind}" + (f" · dim={m.dim}" if m.dim else ""),
                url="/models",
                icon="cpu",
            )
        )

    # providers
    providers = (
        (
            await session.execute(
                select(Provider)
                .where(
                    Provider.deleted_at.is_(None),
                    or_(
                        Provider.code.ilike(like),
                        Provider.name.ilike(like),
                    ),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for p in providers:
        out.append(
            SearchResult(
                type="provider",
                id=p.id,
                title=p.name or p.code,
                snippet=_truncate(p.base_url or p.code),
                url="/providers",
                icon="cloud",
            )
        )

    # kbs
    kbs = (
        (
            await session.execute(
                select(KnowledgeBase)
                .where(
                    KnowledgeBase.deleted_at.is_(None),
                    or_(
                        KnowledgeBase.kb_key.ilike(like),
                        KnowledgeBase.name.ilike(like),
                    ),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for kb in kbs:
        out.append(
            SearchResult(
                type="kb",
                id=kb.id,
                title=kb.name or kb.kb_key,
                snippet=_truncate(kb.kb_key),
                url="/kbs",
                icon="library",
            )
        )

    # users
    users = (
        (
            await session.execute(
                select(User)
                .where(
                    User.deleted_at.is_(None),
                    or_(
                        User.username.ilike(like),
                        User.email.ilike(like),
                        User.display_name.ilike(like),
                    ),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for u in users:
        out.append(
            SearchResult(
                type="user",
                id=u.id,
                title=u.display_name or u.username,
                snippet=_truncate(u.email or u.username),
                url="/users",
                icon="users",
            )
        )

    # embed_configs
    embeds = (
        (
            await session.execute(
                select(EmbedConfig)
                .where(
                    EmbedConfig.deleted_at.is_(None),
                    or_(
                        EmbedConfig.embed_key.ilike(like),
                        EmbedConfig.name.ilike(like),
                    ),
                )
                .limit(per)
            )
        )
        .scalars()
        .all()
    )
    for ec in embeds:
        out.append(
            SearchResult(
                type="embed_config",
                id=ec.id,
                title=ec.name or ec.embed_key,
                snippet=_truncate(ec.embed_key),
                url="/embed-configs",
                icon="puzzle",
            )
        )

    return Result.ok(SearchResponse(results=out[:limit]))
