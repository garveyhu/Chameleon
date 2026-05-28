#!/usr/bin/env python3
"""ORM vs DB 字段一致性检查 —— 防 S1 类事故重演

背景：migration 加列但 ORM 没同步声明 → 字段静默丢失（如 embed_configs.api_key_id /
call_logs.end_user_id 都踩过）。Python AttributeError 触发的时机晚于 service 调用，
本地不一定能立刻发现。本脚本一行命令做全量 diff。

用法：
    cd backend && .venv/bin/python ../scripts/check-orm-db-drift.py

退出码：
    0 = 完全一致（或仅有受控的"故意 ORM 不映射"列）
    1 = 发现字段不一致

豁免：在 ALLOWED_DB_ONLY 里列出"DB 有 / ORM 故意没声明"的字段（如 PG GENERATED 列）。
"""
from __future__ import annotations

import asyncio
import sys

# DB 有但 ORM 故意不声明的字段（PG GENERATED / tsvector 等）
ALLOWED_DB_ONLY: dict[str, set[str]] = {
    "chunks": {"content_tsv"},  # PG GENERATED STORED tsvector，召回 SQL 里用 literal_column
}


async def main() -> int:
    import chameleon.core.models  # 触发所有 ORM model 声明
    from chameleon.core.config.inventory import database_url
    from chameleon.core.models.base import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    url = database_url()
    print(f"DB: {url.split('@')[-1][:60]}\n")
    engine = create_async_engine(url)

    orm_tables = {
        t.name: {c.name for c in t.columns} for t in Base.metadata.sorted_tables
    }

    async with engine.connect() as conn:
        def inspect_db(sync_conn):
            from sqlalchemy import inspect

            insp = inspect(sync_conn)
            return {
                t: {c["name"] for c in insp.get_columns(t)}
                for t in insp.get_table_names()
            }

        db_tables = await conn.run_sync(inspect_db)

    print(f"ORM 表: {len(orm_tables)}    DB 表: {len(db_tables)}")

    has_issue = False
    shared = sorted(set(orm_tables) & set(db_tables))
    for t in shared:
        in_db_not_orm = db_tables[t] - orm_tables[t] - ALLOWED_DB_ONLY.get(t, set())
        in_orm_not_db = orm_tables[t] - db_tables[t]
        if in_db_not_orm:
            has_issue = True
            print(f"  ⚠️  [{t}] DB 有 / ORM 缺：{sorted(in_db_not_orm)}")
        if in_orm_not_db:
            has_issue = True
            print(f"  ⚠️  [{t}] ORM 有 / DB 缺：{sorted(in_orm_not_db)}")

    db_only = set(db_tables) - set(orm_tables) - {"alembic_version"}
    if db_only:
        print(f"\n📋 仅 DB 有的表（不影响 ORM 调用，但可能是孤儿）：{sorted(db_only)}")
    orm_only = set(orm_tables) - set(db_tables)
    if orm_only:
        has_issue = True
        print(f"\n⚠️  仅 ORM 有的表（查询必失败）：{sorted(orm_only)}")

    await engine.dispose()

    if not has_issue:
        print("\n✅ ORM 与 DB 字段一致（豁免 ALLOWED_DB_ONLY 中的故意不映射列）")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
