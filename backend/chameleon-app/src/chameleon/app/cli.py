"""chameleon CLI 入口

命令：
  chameleon init-admin --name <name>       —— 落第一个 admin key（明文回显一次）
  chameleon db upgrade                     —— 应用 alembic 迁移
  chameleon db downgrade <revision>        —— 回滚
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import click
from sqlalchemy import select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.infra.logger import setup_logger
from chameleon.data.models import ApiKey
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key


@click.group()
def cli() -> None:
    """Chameleon 命令行工具"""
    setup_logger()


@cli.command("init-admin")
@click.option("--name", default="admin", help="管理员名称（用于 api_keys.name）")
@click.option(
    "--app-id",
    default="admin-cli",
    help="app_id（用于 api_keys.app_id；默认 admin-cli）",
)
@click.option("--force", is_flag=True, help="即使已有 admin key 也强制新建（不建议）")
def init_admin(name: str, app_id: str, force: bool) -> None:
    """落第一个 admin scope api_key。明文仅一次回显，请立即保存。"""
    asyncio.run(_init_admin_async(name=name, app_id=app_id, force=force))


async def _init_admin_async(*, name: str, app_id: str, force: bool) -> None:
    async with AsyncSessionLocal() as session:
        # 检查是否已有 admin key（scopes 是 JSON 列，Python 端 filter 即可）
        active_keys = (
            (await session.execute(select(ApiKey).where(ApiKey.revoked_at.is_(None))))
            .scalars()
            .all()
        )
        existing = next((k for k in active_keys if "admin" in (k.scopes or [])), None)

        if existing and not force:
            click.echo(
                click.style(
                    f"✗ 已存在 admin key (app_id={existing.app_id})。"
                    "如确需新建追加 --force",
                    fg="red",
                )
            )
            sys.exit(1)

        created = await create_api_key(
            session,
            CreateApiKeyRequest(
                app_id=app_id,
                name=name,
                scopes=["admin"],
                description="bootstrapped via `chameleon init-admin`",
            ),
            created_by_user_id=None,
        )
        await session.commit()

    click.echo(click.style("✓ Admin API key created", fg="green", bold=True))
    click.echo(f"  app_id : {created.app_id}")
    click.echo(f"  name   : {created.name}")
    click.echo(f"  scopes : {created.scopes}")
    click.echo()
    click.echo(click.style("  KEY (仅一次回显，请立即保存)：", fg="yellow", bold=True))
    click.echo(click.style(f"  {created.plain_key}", fg="cyan", bold=True))
    click.echo()
    click.echo(
        "  用法： curl -H 'Authorization: Bearer <KEY>' http://localhost:7009/v1/..."
    )


@cli.group("db")
def db_group() -> None:
    """数据库迁移命令"""


@db_group.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision: str) -> None:
    """alembic upgrade <revision> (默认 head)"""
    rc = subprocess.call(["alembic", "upgrade", revision])
    sys.exit(rc)


@db_group.command("downgrade")
@click.argument("revision")
def db_downgrade(revision: str) -> None:
    """alembic downgrade <revision>"""
    rc = subprocess.call(["alembic", "downgrade", revision])
    sys.exit(rc)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
