"""LLMNode —— 调 LLM 生成

data 配置：
    {
      "model_name": "qwen-plus",            # 可选；不传走默认（cases.llm）
      "system_prompt": "You are helpful.",   # 可选
      "prompt_template": "Q: {query}\\nA:",  # 可选；Python str.format 渲染 input.* 字段
      "temperature": 0.7,                    # 可选；覆盖 model 默认
      "max_tokens": null,                    # 可选
    }

input:
    上游传入的整个 dict（用 prompt_template 时直接 .format(**input)）；
    或字符串（当 query 用）；
    或 list[{role, content}]（直接当 messages）。

output:
    {
      "answer": "...",
      "usage": {"prompt_tokens", "completion_tokens", "total_tokens"} | None,
      "model": "qwen-plus",
    }
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.executor import register_node_type
from chameleon.core.graph.node_base import Node


def _build_messages(
    input: Any, system_prompt: str | None, prompt_template: str | None
) -> list:
    """根据 input 形态 + 模板生成 langchain messages 列表"""
    msgs: list = []
    if system_prompt:
        msgs.append(SystemMessage(content=system_prompt))

    # 形态 1：list[{role, content}] 直接当对话历史
    if isinstance(input, list) and all(
        isinstance(m, dict) and "role" in m and "content" in m for m in input
    ):
        for m in input:
            role = m["role"]
            content = m["content"]
            if role == "system":
                msgs.append(SystemMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
            else:
                msgs.append(HumanMessage(content=content))
        return msgs

    # 形态 2：dict + prompt_template → 用 format 渲染
    if isinstance(input, dict) and prompt_template:
        try:
            rendered = prompt_template.format(**input)
        except (KeyError, IndexError) as e:
            raise ValueError(
                f"prompt_template 渲染失败（缺字段 {e}）；input keys: {list(input.keys())}"
            ) from e
        msgs.append(HumanMessage(content=rendered))
        return msgs

    # 形态 3：字符串当 query
    if isinstance(input, str):
        msgs.append(HumanMessage(content=input))
        return msgs

    # 形态 4：dict 但没模板 —— 取常见字段当 user message
    if isinstance(input, dict):
        for key in ("query", "question", "input", "text"):
            v = input.get(key)
            if isinstance(v, str) and v.strip():
                msgs.append(HumanMessage(content=v))
                # 把上下文也拼上（KB 节点的 joined_context 风格）
                ctx_text = input.get("joined_context")
                if isinstance(ctx_text, str) and ctx_text.strip():
                    msgs[-1] = HumanMessage(
                        content=f"参考资料：\n{ctx_text}\n\n问题：{v}"
                    )
                return msgs

    raise ValueError(
        f"LLMNode 无法从 input 构造 messages：type={type(input).__name__}"
    )


def _extract_usage(message) -> dict[str, int] | None:
    """从 langchain AIMessage 抽 usage（兼容字段差异）"""
    meta = getattr(message, "usage_metadata", None) or {}
    if not meta:
        meta = getattr(message, "response_metadata", {}).get(
            "token_usage", {}
        ) or {}
    if not meta:
        return None
    # 兼容 langchain usage_metadata 命名（input_tokens/output_tokens）
    prompt = meta.get("input_tokens") or meta.get("prompt_tokens") or 0
    completion = (
        meta.get("output_tokens")
        or meta.get("completion_tokens")
        or 0
    )
    total = meta.get("total_tokens") or (prompt + completion)
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total),
    }


class LLMNode(Node[Any, dict]):
    """LLM 调用节点

    spec.data 可选：
      model_name / system_prompt / prompt_template / temperature / max_tokens /
      tool_keys: ["http", "sql", ...]    —— 启用 OpenAI function calling
                                          模型选哪个 tool 就返其 name + args，
                                          不会自动执行；executor 由后续节点接管
    """

    type = "llm"

    def validate_data(self, data: dict[str, Any]) -> None:
        if "temperature" in data and data["temperature"] is not None:
            t = float(data["temperature"])
            if not 0.0 <= t <= 2.0:
                raise ValueError(
                    f"LLMNode.data.temperature 必须 [0, 2]，得到 {t}"
                )
        if "max_tokens" in data and data["max_tokens"] is not None:
            n = int(data["max_tokens"])
            if n < 1:
                raise ValueError("LLMNode.data.max_tokens 必须 ≥ 1")
        tks = data.get("tool_keys")
        if tks is not None:
            if not isinstance(tks, list) or not all(
                isinstance(x, str) for x in tks
            ):
                raise ValueError("LLMNode.data.tool_keys 必须是 list[str]")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        from chameleon.core.components.llms.factory import llm as get_llm

        model_name = self.spec.data.get("model_name")
        system_prompt = self.spec.data.get("system_prompt")
        prompt_template = self.spec.data.get("prompt_template")

        client = get_llm(model_name)
        messages = _build_messages(input, system_prompt, prompt_template)

        # temperature / max_tokens 覆盖
        invoke_kwargs: dict[str, Any] = {}
        if self.spec.data.get("temperature") is not None:
            invoke_kwargs["temperature"] = float(self.spec.data["temperature"])
        if self.spec.data.get("max_tokens") is not None:
            invoke_kwargs["max_tokens"] = int(self.spec.data["max_tokens"])

        # function calling：转 OpenAI tools 协议 + bind
        tool_keys = self.spec.data.get("tool_keys") or []
        if tool_keys:
            client = _bind_tools(client, tool_keys)

        logger.debug(
            "LLMNode {} | model={} | msgs={} | tools={}",
            self.id,
            model_name or "<default>",
            len(messages),
            tool_keys,
        )

        ai_msg = await client.ainvoke(messages, **invoke_kwargs)
        content = (
            ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
        )

        # tool_calls：模型决定调哪个 tool，返结构化 list（不自动执行）
        tool_calls = _extract_tool_calls(ai_msg)

        return {
            "answer": content,
            "tool_calls": tool_calls,
            "usage": _extract_usage(ai_msg),
            "model": getattr(client, "model_name", None) or model_name,
        }


def _bind_tools(client, tool_keys: list[str]):
    """把 tool_keys 转 OpenAI tools 协议 + 绑到 langchain client

    langchain 的 ChatOpenAI 子类支持 .bind_tools([...])；不支持时返回原 client。
    """
    from chameleon.core.tools import get_tool_class

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
    if not schemas:
        return client

    if hasattr(client, "bind_tools"):
        try:
            return client.bind_tools(schemas)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "LLMNode bind_tools failed; falling back to no-tools: {}", e
            )
    return client


def _extract_tool_calls(ai_msg) -> list[dict[str, Any]]:
    """从 langchain AIMessage 抽出 tool_calls（统一格式）

    返：[{ "name": "http", "args": {...}, "id": "call_xxx" }, ...]
    """
    raw = getattr(ai_msg, "tool_calls", None) or []
    out: list[dict[str, Any]] = []
    for tc in raw:
        # langchain 把 tool_calls 规范化为 dict 形态
        if isinstance(tc, dict):
            out.append(
                {
                    "name": tc.get("name"),
                    "args": tc.get("args") or {},
                    "id": tc.get("id"),
                }
            )
        else:
            # 兼容 ToolCall pydantic 对象
            out.append(
                {
                    "name": getattr(tc, "name", None),
                    "args": getattr(tc, "args", None) or {},
                    "id": getattr(tc, "id", None),
                }
            )
    return out


register_node_type(LLMNode)
