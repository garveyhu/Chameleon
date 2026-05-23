"""P18.2 PR #22 单元 + 集成测试"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from chameleon.core.tools import (
    Tool,
    ToolContext,
    ToolResult,
    get_tool_class,
    list_tool_keys,
)
from chameleon.core.tools.base import _validate_args
from chameleon.core.tools.builtins.http import HTTPTool
from chameleon.core.tools.builtins.sql import SQLTool


# ── registry ─────────────────────────────────────────────


def test_builtin_tools_registered():
    keys = list_tool_keys()
    assert "http" in keys
    assert "sql" in keys


def test_get_tool_class_returns_class():
    assert get_tool_class("http") is HTTPTool
    assert get_tool_class("sql") is SQLTool


def test_unknown_tool_returns_none():
    assert get_tool_class("ghost") is None


# ── args 校验 ────────────────────────────────────────────


def test_validate_args_required_missing():
    schema = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }
    with pytest.raises(ValueError, match="缺少必填字段"):
        _validate_args({}, schema)


def test_validate_args_type_mismatch():
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
    }
    with pytest.raises(ValueError, match="类型不匹配"):
        _validate_args({"n": "not-an-int"}, schema)


def test_validate_args_enum():
    schema = {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["GET", "POST"]}
        },
    }
    with pytest.raises(ValueError, match="enum|必须在"):
        _validate_args({"method": "DELETE"}, schema)
    _validate_args({"method": "GET"}, schema)  # OK


# ── HTTPTool ─────────────────────────────────────────────


@pytest.mark.respx(base_url="https://api.example.com")
async def test_http_tool_get_ok(respx_mock):
    respx_mock.get("/ping").mock(
        return_value=Response(
            200,
            json={"pong": True},
            headers={"content-type": "application/json"},
        )
    )
    tool = HTTPTool(
        config={"allowed_url_prefixes": ["https://api.example.com/"]}
    )
    r = await tool.run_with_validation(
        {"method": "GET", "url": "https://api.example.com/ping"},
        ToolContext(),
    )
    assert r.ok is True
    assert r.data["status"] == 200
    assert r.data["body"] == {"pong": True}


@pytest.mark.respx(base_url="https://api.example.com")
async def test_http_tool_url_not_whitelisted():
    tool = HTTPTool(
        config={"allowed_url_prefixes": ["https://api.example.com/"]}
    )
    r = await tool.run_with_validation(
        {"method": "GET", "url": "https://evil.com/x"},
        ToolContext(),
    )
    assert r.ok is False
    assert "白名单" in r.error


async def test_http_tool_invalid_method():
    tool = HTTPTool()
    r = await tool.run_with_validation(
        {"method": "PATCH", "url": "https://x.com/"},
        ToolContext(),
    )
    assert r.ok is False
    assert "enum" in r.error or "必须在" in r.error


@pytest.mark.respx
async def test_http_tool_500_returns_ok_false(respx_mock):
    respx_mock.get("https://api.example.com/boom").mock(
        return_value=Response(500, text="oh no")
    )
    tool = HTTPTool(
        config={"allowed_url_prefixes": ["https://api.example.com/"]}
    )
    r = await tool.run_with_validation(
        {"method": "GET", "url": "https://api.example.com/boom"},
        ToolContext(),
    )
    assert r.ok is False
    assert "HTTP 500" in r.error


# ── SQLTool ──────────────────────────────────────────────


async def test_sql_tool_requires_whitelist():
    tool = SQLTool()
    r = await tool.run_with_validation(
        {
            "db_url": "postgresql+asyncpg://localhost/x",
            "sql": "SELECT 1",
        },
        ToolContext(),
    )
    assert r.ok is False
    assert "白名单" in r.error or "allowed_db_urls" in r.error


async def test_sql_tool_db_url_not_in_whitelist():
    tool = SQLTool(
        config={"allowed_db_urls": ["postgresql+asyncpg://prod/x"]}
    )
    r = await tool.run_with_validation(
        {
            "db_url": "postgresql+asyncpg://other/x",
            "sql": "SELECT 1",
        },
        ToolContext(),
    )
    assert r.ok is False
    assert "白名单" in r.error


async def test_sql_tool_rejects_non_select():
    tool = SQLTool(
        config={"allowed_db_urls": ["postgresql+asyncpg://localhost/x"]}
    )
    for bad in (
        "INSERT INTO t VALUES(1)",
        "DELETE FROM t WHERE 1=1",
        "DROP TABLE t",
        "UPDATE t SET x=1",
    ):
        r = await tool.run_with_validation(
            {
                "db_url": "postgresql+asyncpg://localhost/x",
                "sql": bad,
            },
            ToolContext(),
        )
        assert r.ok is False
        assert "SELECT" in r.error or "禁用" in r.error


async def test_sql_tool_rejects_forbidden_inside_select():
    tool = SQLTool(
        config={"allowed_db_urls": ["postgresql+asyncpg://localhost/x"]}
    )
    # 以 SELECT 开头但含禁用关键字
    r = await tool.run_with_validation(
        {
            "db_url": "postgresql+asyncpg://localhost/x",
            "sql": "SELECT * FROM t; DROP TABLE t",
        },
        ToolContext(),
    )
    assert r.ok is False
    assert "禁用" in r.error


# ── 真跑一次 SELECT（用现有项目 DB） ───────────────────────


async def test_sql_tool_real_select():
    """跑一条真 SELECT 验证集成路径 OK；用项目自身 DB"""
    from chameleon.core.config import inventory

    db_url = inventory.database_url()
    tool = SQLTool(config={"allowed_db_urls": [db_url]})
    r = await tool.run_with_validation(
        {"db_url": db_url, "sql": "SELECT 1 AS one", "limit": 5},
        ToolContext(),
    )
    assert r.ok is True, r.error
    assert r.data["columns"] == ["one"]
    assert r.data["rows"] == [{"one": 1}]
    assert r.data["row_count"] == 1
