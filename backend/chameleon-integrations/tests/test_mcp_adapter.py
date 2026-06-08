"""MCP 适配单测：CallToolResult 摊平 + tool→描述符（不需真 MCP server）。"""

from __future__ import annotations

import pytest

from chameleon.integrations.mcp.adapter import _make_descriptor
from chameleon.integrations.mcp.client import flatten_tool_result


class _TextContent:
    type = "text"
    text = "hello world"


class _Result:
    isError = False
    structuredContent = None
    content = [_TextContent()]


class _StructResult:
    isError = False
    structuredContent = {"answer": 42}
    content = []


class _ErrResult:
    isError = True
    structuredContent = None
    content = [type("C", (), {"type": "text", "text": "boom"})()]


class _Tool:
    name = "echo"
    description = "回显"
    inputSchema = {"type": "object", "properties": {"x": {"type": "string"}}}


class _FakeSession:
    def __init__(self, result):
        self._result = result
        self.called = None

    async def call_tool(self, name, args):
        self.called = (name, args)
        return self._result


def test_flatten_text():
    assert flatten_tool_result(_Result()) == {
        "ok": True, "data": "hello world", "error": None,
    }


def test_flatten_structured():
    out = flatten_tool_result(_StructResult())
    assert out["ok"] is True and out["data"] == {"answer": 42}


def test_flatten_error():
    out = flatten_tool_result(_ErrResult())
    assert out["ok"] is False and out["error"] == "boom"


@pytest.mark.asyncio
async def test_make_descriptor_and_handler():
    session = _FakeSession(_Result())
    d = _make_descriptor(session, _Tool(), "echo")
    assert d.name == "echo"
    assert d.description == "回显"
    assert d.parameters_schema["properties"]["x"]["type"] == "string"
    # handler 调通 → session.call_tool 收到真名 + args，返摊平结果
    r = await d.handler(x="1")
    assert session.called == ("echo", {"x": "1"})
    assert r["data"] == "hello world"
