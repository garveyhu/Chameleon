"""SQLTool —— 只读 SQL 查询工具

红线：
- 只允许 SELECT（白名单 SQL 关键字开头校验）
- db_url 必须在 config.allowed_db_urls 白名单内
- 超时 30s 强制
- LIMIT 缺失时自动包一层 SELECT * FROM (...) LIMIT N

参数：
    {
      "db_url": "postgresql+asyncpg://...",  # 必须在白名单
      "sql": "SELECT ...",
      "limit": 100,                           # 最大 1000
      "timeout": 30                            # 秒
    }

config：
    {
      "allowed_db_urls": ["postgresql+asyncpg://localhost/test"],
      "max_limit": 1000,
      "default_timeout": 30
    }

返回：
    ToolResult(data={"columns": [...], "rows": [...], "row_count": N})

P18.1：默认 disabled（default_enabled=False）。admin 显式开启 + 配 allowed_db_urls 才能用。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from chameleon.core.tools.base import Tool, ToolContext, ToolResult
from chameleon.core.tools.registry import register_tool

# 严格白名单：只允许这些 SQL 起始关键字
_ALLOWED_PREFIX = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

# 禁止字段：即便是 SELECT 也不允许出现这些（防嵌套修改）
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|COPY|VACUUM|"
    r"REINDEX|CLUSTER|REFRESH|CALL|DO|EXECUTE)\b",
    re.IGNORECASE,
)

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000
_DEFAULT_TIMEOUT = 30.0


class SQLTool(Tool):
    tool_key = "sql"
    description = "只读 SQL 查询（仅 SELECT/WITH；按白名单 db_url 限制）"
    default_enabled = False  # 不安全，默认关

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "db_url": {"type": "string"},
                "sql": {"type": "string"},
                "limit": {"type": "integer"},
                "timeout": {"type": "number"},
            },
            "required": ["db_url", "sql"],
        }

    async def run(
        self, args: dict[str, Any], ctx: ToolContext
    ) -> ToolResult:
        db_url = args["db_url"]
        sql = args["sql"]

        allowed = self.config.get("allowed_db_urls") or []
        if not allowed:
            return ToolResult(
                ok=False,
                error="SQLTool 未配置 allowed_db_urls；admin 必须显式声明白名单",
            )
        if db_url not in allowed:
            return ToolResult(
                ok=False,
                error=f"db_url 不在白名单内（{len(allowed)} 条配置）",
            )

        # SQL 白名单校验
        if not _ALLOWED_PREFIX.search(sql):
            return ToolResult(
                ok=False,
                error="只允许 SELECT / WITH 开头的查询",
            )
        if _FORBIDDEN_KEYWORDS.search(sql):
            return ToolResult(
                ok=False,
                error="SQL 含禁用关键字（DML/DDL 一律拒绝）",
            )

        limit = min(
            int(args.get("limit") or _DEFAULT_LIMIT),
            int(self.config.get("max_limit") or _MAX_LIMIT),
        )
        timeout = float(
            args.get("timeout")
            or self.config.get("default_timeout")
            or _DEFAULT_TIMEOUT
        )

        # 强制 LIMIT（包一层 outer query）
        wrapped_sql = f"SELECT * FROM (\n{sql}\n) _wrapper LIMIT {limit}"

        engine = create_async_engine(db_url, pool_pre_ping=True)
        try:
            async with asyncio.timeout(timeout):
                async with engine.connect() as conn:
                    result = await conn.execute(text(wrapped_sql))
                    rows = [dict(r._mapping) for r in result.fetchall()]
                    columns = list(result.keys())
        except asyncio.TimeoutError:
            return ToolResult(
                ok=False, error=f"SQL 超时（> {timeout}s）"
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                ok=False, error=f"执行失败: {type(e).__name__}: {str(e)[:300]}"
            )
        finally:
            await engine.dispose()

        logger.debug(
            "SQLTool | db={} | rows={} | limit={}",
            db_url.split("@")[-1] if "@" in db_url else db_url,
            len(rows),
            limit,
        )

        return ToolResult(
            ok=True,
            data={
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            },
            meta={"limit": limit},
        )


register_tool(SQLTool)
