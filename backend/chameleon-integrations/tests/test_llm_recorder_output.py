"""LLM 记录器输出捕获——结构化输出 / 工具调用回退（修：trace 输出列对 ctx.route /
ctx.complete(schema=) 等结构化调用不再为空）。"""

from __future__ import annotations

from types import SimpleNamespace as NS

from chameleon.integrations.observe.llm_recorder import _output_text


def _resp(message):  # noqa: ANN001
    return NS(generations=[[NS(message=message)]])


def test_output_prefers_text_content():
    msg = NS(content="审批结果：拒绝", tool_calls=[])
    assert _output_text(_resp(msg)) == "审批结果：拒绝"


def test_output_falls_back_to_tool_calls_when_content_empty():
    # with_structured_output(function_calling)：结果落 tool_calls.args、content 空
    msg = NS(content="", tool_calls=[{"name": "structured_output", "args": {"name": "张三", "age": 28}}])
    out = _output_text(_resp(msg))
    assert "张三" in out and "28" in out and "structured_output" in out


def test_output_empty_when_neither_content_nor_tool_calls():
    assert _output_text(_resp(NS(content="", tool_calls=[]))) == ""


def test_output_handles_object_style_tool_call():
    # 部分 LangChain 版本 tool_calls 元素是对象而非 dict
    tc = NS(name="route", args={"agent_key": "sql-bot"})
    out = _output_text(_resp(NS(content="", tool_calls=[tc])))
    assert "sql-bot" in out and "route" in out
