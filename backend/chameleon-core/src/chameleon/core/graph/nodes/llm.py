"""LLMNode —— 调 LLM 生成（含流式 / Memory / 多轮 tool_call，v1.1 PR A2）

data 配置：
    {
      "model_name": "qwen-plus",            # 可选；不传走默认（cases.llm）
      "system_prompt": "You are helpful.",   # 可选
      "prompt_template": "Q: {query}\\nA:",  # 可选；Python str.format 渲染 input.* 字段
      "temperature": 0.7,                    # 可选；覆盖 model 默认
      "max_tokens": null,                    # 可选
      "memory_window": 10,                   # 可选；多轮历史保留最近 N 条
      "tool_keys": ["http", "sql"],          # 可选；启用 OpenAI function calling
      "max_tool_rounds": 3,                  # 可选；agentic 循环最多轮数（hard cap 8）
    }

input：上游 dict（含 history 时走 Memory）/ 字符串 / list[{role, content}] 对话历史。
       见 llm_messages.build_messages 的各形态。

output：
    {
      "answer": "...",
      "tool_calls": [...],        # 最后一轮模型选的 tool（无则空）
      "tool_rounds": [...],       # 多轮 tool_call 执行轨迹（trace tree 串联用）
      "rounds_used": 1,
      "usage": {...} | None,
      "model": "qwen-plus",
    }

流式：execute_stream 走 astream，逐 token emit；execute 走 ainvoke（batch）。
两条路径共用同一 agentic 循环（_run）。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import DeltaSink, Node
from chameleon.core.graph.nodes.llm_messages import build_messages
from chameleon.core.graph.nodes.llm_tools import (
    bind_tools,
    extract_tool_calls,
    extract_usage,
    merge_usage,
    run_tool_calls,
)
from chameleon.core.graph.registry import register_node_type

#: agentic tool 循环默认轮数
DEFAULT_MAX_TOOL_ROUNDS = 3
#: 硬上限（防 prompt 注入把模型卡在无限工具调用）
MAX_TOOL_ROUNDS_HARD_CAP = 8


class LLMNode(Node[Any, dict]):
    """LLM 调用节点

    spec.data 可选：model_name / system_prompt / prompt_template / temperature /
    max_tokens / memory_window / tool_keys / max_tool_rounds。

    tool_keys 非空时进入 agentic 循环：模型选 tool → 执行 → 回填结果 → 再调模型，
    直到模型给出无 tool_call 的最终答案，或达到 max_tool_rounds。
    """

    type = "llm"

    def validate_data(self, data: dict[str, Any]) -> None:
        if data.get("temperature") is not None:
            t = float(data["temperature"])
            if not 0.0 <= t <= 2.0:
                raise ValueError(f"LLMNode.data.temperature 必须 [0, 2]，得到 {t}")
        if data.get("max_tokens") is not None:
            if int(data["max_tokens"]) < 1:
                raise ValueError("LLMNode.data.max_tokens 必须 ≥ 1")
        if data.get("memory_window") is not None:
            if int(data["memory_window"]) < 1:
                raise ValueError("LLMNode.data.memory_window 必须 ≥ 1")
        tks = data.get("tool_keys")
        if tks is not None and (
            not isinstance(tks, list) or not all(isinstance(x, str) for x in tks)
        ):
            raise ValueError("LLMNode.data.tool_keys 必须是 list[str]")
        if data.get("max_tool_rounds") is not None:
            mr = int(data["max_tool_rounds"])
            if not 1 <= mr <= MAX_TOOL_ROUNDS_HARD_CAP:
                raise ValueError(
                    f"LLMNode.data.max_tool_rounds 必须 [1, {MAX_TOOL_ROUNDS_HARD_CAP}]"
                )

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        """非流式：batch 调用（emit=None）"""
        return await self._run(ctx, input, emit=None)

    async def execute_stream(
        self, ctx: NodeContext, input: Any, emit: DeltaSink | None
    ) -> dict:
        """流式：emit 非空时逐 token 推；为空时退化为 batch"""
        return await self._run(ctx, input, emit=emit)

    # ── 核心：agentic 循环（流式 / 非流式共用）──────────────────

    async def _run(
        self, ctx: NodeContext, input: Any, emit: DeltaSink | None
    ) -> dict:
        from chameleon.core.components.llms.factory import llm as get_llm

        data = self.spec.data
        model_name = data.get("model_name")
        memory_window = data.get("memory_window")
        tool_keys = data.get("tool_keys") or []
        max_rounds = int(data.get("max_tool_rounds") or DEFAULT_MAX_TOOL_ROUNDS)

        invoke_kwargs: dict[str, Any] = {}
        if data.get("temperature") is not None:
            invoke_kwargs["temperature"] = float(data["temperature"])
        if data.get("max_tokens") is not None:
            invoke_kwargs["max_tokens"] = int(data["max_tokens"])

        raw_client = get_llm(model_name)
        client = bind_tools(raw_client, tool_keys) if tool_keys else raw_client

        messages = build_messages(
            input,
            data.get("system_prompt"),
            data.get("prompt_template"),
            memory_window=memory_window,
        )

        logger.debug(
            "LLMNode {} | model={} | msgs={} | tools={} | stream={}",
            self.id,
            model_name or "<default>",
            len(messages),
            tool_keys,
            emit is not None,
        )

        usage: dict[str, int] | None = None
        tool_rounds: list[dict[str, Any]] = []
        last_tool_calls: list[dict[str, Any]] = []
        content = ""
        rounds_used = 0

        for _ in range(max_rounds):
            rounds_used += 1
            # 只在「不会再有工具回合」时流式 token：有 tool_keys 时中间回合
            # 内容通常为空（只出 tool_calls），最终回合无 tool_calls 才有正文，
            # astream 累积天然处理；故流式始终走 astream（emit 非空时）。
            ai_msg = await self._invoke(client, messages, emit, invoke_kwargs)
            usage = merge_usage(usage, extract_usage(ai_msg))
            content = (
                ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
            )
            tcs = extract_tool_calls(ai_msg)
            last_tool_calls = tcs

            if not tcs:
                break  # 最终答案，结束循环

            # 有 tool_calls：回填 assistant turn + 工具结果，继续下一轮
            messages.append(ai_msg)
            tool_messages, records = await run_tool_calls(tcs, ctx, self.id)
            messages.extend(tool_messages)
            tool_rounds.append(
                {
                    "round": rounds_used,
                    "assistant": content,
                    "tool_calls": tcs,
                    "tool_results": records,
                }
            )

        return {
            "answer": content,
            "tool_calls": last_tool_calls,
            "tool_rounds": tool_rounds,
            "rounds_used": rounds_used,
            "usage": usage,
            "model": getattr(raw_client, "model_name", None) or model_name,
        }

    async def _invoke(
        self,
        client,
        messages: list,
        emit: DeltaSink | None,
        invoke_kwargs: dict[str, Any],
    ):
        """单次 LLM 调用：emit 为空 → ainvoke；否则 astream 逐 token emit + 累积"""
        if emit is None:
            return await client.ainvoke(messages, **invoke_kwargs)

        merged = None
        async for chunk in client.astream(messages, **invoke_kwargs):
            text = getattr(chunk, "content", None)
            if isinstance(text, str) and text:
                await emit(text)
            merged = chunk if merged is None else merged + chunk
        if merged is None:
            # 空流兜底（极少见）
            return await client.ainvoke(messages, **invoke_kwargs)
        return merged


register_node_type(LLMNode)
