"""ReAct / function-calling 循环原语 —— graph LLMNode / agentkit 共用。

从 `engine/graph/nodes/llm_tools.py` 下沉到 integrations，去掉 graph（NodeContext）
依赖：纯函数（bind_tools / extract_* / merge_usage）原样搬来；`run_tool_calls`
改成 graph 无关的通用签名（收 caller/related_id/extra，而非 NodeContext），底层
走 `integrations.tools.execute.run_tool`。graph LLMNode 留一层薄封装从 NodeContext
取这些字段后转调本函数。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import ToolMessage
from loguru import logger

from chameleon.integrations.tools.execute import run_tool
from chameleon.integrations.tools.registry import get_tool_class


def bind_tools(client, tool_keys: list[str]):  # noqa: ANN001
    """把 tool_keys 转 OpenAI tools 协议 + 绑到 langchain client。

    langchain 的 ChatOpenAI 子类支持 .bind_tools([...])；不支持时返回原 client。
    """
    schemas = tool_schemas(tool_keys)
    if not schemas:
        return client
    return bind_schemas(client, schemas)


def tool_schemas(tool_keys: list[str]) -> list[dict[str, Any]]:
    """把已注册的 tool_keys 转成 OpenAI function-calling schema 列表。"""
    schemas: list[dict[str, Any]] = []
    for key in tool_keys:
        cls = get_tool_class(key)
        if cls is None:
            continue
        tool = cls()
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": cls.tool_key,
                    "description": cls.description,
                    "parameters": tool.parameters_schema(),
                },
            }
        )
    return schemas


def bind_schemas(client, schemas: list[dict[str, Any]]):  # noqa: ANN001
    """把已组装的 OpenAI tool schema 列表绑到 langchain client（容错）。"""
    if not schemas:
        return client
    if hasattr(client, "bind_tools"):
        try:
            return client.bind_tools(schemas)
        except Exception as e:  # noqa: BLE001
            logger.warning("bind_tools failed; falling back to no-tools: {}", e)
    return client


def extract_tool_calls(ai_msg) -> list[dict[str, Any]]:  # noqa: ANN001
    """从 langchain AIMessage 抽出 tool_calls（统一格式）。

    返：[{ "name": "http", "args": {...}, "id": "call_xxx" }, ...]
    """
    raw = getattr(ai_msg, "tool_calls", None) or []
    out: list[dict[str, Any]] = []
    for tc in raw:
        if isinstance(tc, dict):
            out.append(
                {
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                    "id": tc.get("id"),
                }
            )
        else:
            out.append(
                {
                    "name": getattr(tc, "name", None),
                    "args": getattr(tc, "args", None) or {},
                    "id": getattr(tc, "id", None),
                }
            )
    return out


def extract_usage(message) -> dict[str, int] | None:  # noqa: ANN001
    """从 langchain AIMessage 抽 usage（兼容字段差异）。"""
    meta = getattr(message, "usage_metadata", None) or {}
    if not meta:
        meta = getattr(message, "response_metadata", {}).get("token_usage", {}) or {}
    if not meta:
        return None
    prompt = meta.get("input_tokens") or meta.get("prompt_tokens") or 0
    completion = meta.get("output_tokens") or meta.get("completion_tokens") or 0
    total = meta.get("total_tokens") or (prompt + completion)
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total),
    }


def merge_usage(
    acc: dict[str, int] | None, add: dict[str, int] | None
) -> dict[str, int] | None:
    """累加多轮 usage（agentic 循环每轮一次 LLM 调用）。"""
    if add is None:
        return acc
    if acc is None:
        return dict(add)
    return {
        "prompt_tokens": acc["prompt_tokens"] + add["prompt_tokens"],
        "completion_tokens": acc["completion_tokens"] + add["completion_tokens"],
        "total_tokens": acc["total_tokens"] + add["total_tokens"],
    }


async def run_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    caller: str,
    related_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[list[ToolMessage], list[dict[str, Any]]]:
    """跑一轮 tool_calls，返回 (回填给 LLM 的 ToolMessage 列表, 结构化记录)。

    graph 无关的通用版：调用方（graph LLMNode / agentkit runner）传入 caller /
    related_id / extra；底层统一走 `execute.run_tool`，不分叉。单个工具异常被收敛成
    {ok: False, error}，不打断整轮（让模型看到失败再决策）。
    """
    tool_messages: list[ToolMessage] = []
    records: list[dict[str, Any]] = []
    for tc in tool_calls:
        name = tc.get("name") or ""
        args = tc.get("args") or {}
        call_id = tc.get("id") or name
        try:
            result = await run_tool(
                name, args, caller=caller, related_id=related_id, extra=extra
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("tool {} failed: {}", name, e)
            result = {"tool_key": name, "ok": False, "data": None, "error": str(e)[:300]}
        tool_messages.append(
            ToolMessage(
                content=json.dumps(result, ensure_ascii=False, default=str),
                tool_call_id=call_id,
            )
        )
        records.append({"name": name, "args": args, "id": tc.get("id"), "result": result})
    return tool_messages, records
