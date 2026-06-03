"""dashboard 维度 id → 可读名解析。

只对 top-N（≤50）结果的 label 批量 IN 查询，不在主聚合里 join，避免聚合+join 双重
开销与 N+1。无友好名的维度（channel/error_class/session_id 等）返回空映射，前端回退原 id。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import Agent, EmbedConfig, User

EMBED_PREFIX = "embed:"


async def resolve_names(
    session: AsyncSession, dimension: str, labels: list[str]
) -> dict[str, str]:
    """把维度 label 批量解析成可读名（label → display_name）。"""
    keys = [x for x in labels if x and x != "<空>"]
    if not keys:
        return {}

    if dimension == "agent_key":
        rows = (
            await session.execute(
                select(Agent.agent_key, Agent.name).where(Agent.agent_key.in_(keys))
            )
        ).all()
        return {r.agent_key: r.name for r in rows}

    if dimension == "app_id":
        # app_id 形如 "embed:emb_xxx" → 剥前缀查 embed_configs.name；其他前缀原样
        embed_keys = [
            k[len(EMBED_PREFIX) :] for k in keys if k.startswith(EMBED_PREFIX)
        ]
        if not embed_keys:
            return {}
        rows = (
            await session.execute(
                select(EmbedConfig.embed_key, EmbedConfig.name).where(
                    EmbedConfig.embed_key.in_(embed_keys)
                )
            )
        ).all()
        name_by_key = {r.embed_key: r.name for r in rows}
        out: dict[str, str] = {}
        for k in keys:
            if k.startswith(EMBED_PREFIX):
                ek = k[len(EMBED_PREFIX) :]
                if ek in name_by_key:
                    out[k] = f"{name_by_key[ek]}（嵌入）"
        return out

    if dimension == "user_id":
        ids = [int(k) for k in keys if k.lstrip("-").isdigit()]
        if not ids:
            return {}
        rows = (
            await session.execute(
                select(User.id, User.display_name, User.username).where(
                    User.id.in_(ids)
                )
            )
        ).all()
        return {str(r.id): (r.display_name or r.username) for r in rows}

    # model_code / channel / error_class / session_id / end_user_id 本身即可读
    return {}
