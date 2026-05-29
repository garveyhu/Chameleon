"""LLMNode 消息装配 —— input 形态归一化 + Memory buffer（v1.1 PR A2）

从 llm.py 抽出（单一职责）：把异构 input（字符串 / 对话历史 / 上游节点 dict）
+ system_prompt + prompt_template + memory 配置归一成 LangChain messages 列表。

Memory buffer：
- input 直接是 list[{role, content}] → 当完整历史，按 memory_window 取最近 N 条。
- input 是 dict 且含 history: list[{role, content}] → 历史窗口化后，再把当前
  query 字段（query/question/.../answer）作为末条 user 追加。
memory_window=None 不裁剪（保留全部历史）。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

#: 从 dict 取"当前问题"的候选字段（顺序即优先级）
_QUERY_KEYS = ("query", "question", "input", "text", "prompt")
#: 上游节点输出里"答案 / 结果"候选字段
_ANSWER_KEYS = ("answer", "result", "output", "content")


def build_messages(
    input: Any,
    system_prompt: str | None,
    prompt_template: str | None,
    *,
    memory_window: int | None = None,
) -> list:
    """根据 input 形态 + 模板 + memory 配置生成 LangChain messages 列表"""
    msgs: list = []
    if system_prompt:
        msgs.append(SystemMessage(content=system_prompt))

    # 形态 1：list[{role, content}] 直接当对话历史（按 window 取最近）
    if _is_message_list(input):
        msgs.extend(_to_lc_messages(_window(input, memory_window)))
        return msgs

    # Memory：dict 携带 history（历史对话）+ 当前 query
    if isinstance(input, dict) and _is_message_list(input.get("history")):
        msgs.extend(_to_lc_messages(_window(input["history"], memory_window)))
        cur = _extract_query(input)
        if cur:
            ctx_text = input.get("joined_context")
            if isinstance(ctx_text, str) and ctx_text.strip():
                msgs.append(
                    HumanMessage(content=f"参考资料：\n{ctx_text}\n\n问题：{cur}")
                )
            else:
                msgs.append(HumanMessage(content=cur))
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
        # 4a：常见 query 字段（带 KB joined_context 上下文拼接）
        for key in _QUERY_KEYS:
            v = input.get(key)
            if isinstance(v, str) and v.strip():
                ctx_text = input.get("joined_context")
                if isinstance(ctx_text, str) and ctx_text.strip():
                    msgs.append(
                        HumanMessage(content=f"参考资料：\n{ctx_text}\n\n问题：{v}")
                    )
                else:
                    msgs.append(HumanMessage(content=v))
                return msgs

        # 4b：上游节点输出的"答案 / 结果"字段
        for key in _ANSWER_KEYS:
            v = input.get(key)
            if isinstance(v, str) and v.strip():
                msgs.append(HumanMessage(content=v))
                return msgs

        # 4c：兜底 —— 整个 dict 序列化为 JSON 当 user message（dict 永不再抛错）
        msgs.append(
            HumanMessage(content=json.dumps(input, ensure_ascii=False, default=str))
        )
        return msgs

    raise ValueError(
        f"LLMNode 无法从 input 构造 messages：type={type(input).__name__}"
    )


# ── helpers ──────────────────────────────────────────────────


def _is_message_list(v: Any) -> bool:
    """是否为 [{role, content}, ...] 形态"""
    return isinstance(v, list) and bool(v) and all(
        isinstance(m, dict) and "role" in m and "content" in m for m in v
    )


def _window(messages: list[dict], memory_window: int | None) -> list[dict]:
    """按 memory_window 取最近 N 条（None / <=0 不裁剪）"""
    if memory_window is None or memory_window <= 0:
        return messages
    return messages[-memory_window:]


def _to_lc_messages(messages: list[dict]) -> list:
    out: list = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        else:
            out.append(HumanMessage(content=content))
    return out


def _extract_query(input: dict) -> str | None:
    for key in (*_QUERY_KEYS, *_ANSWER_KEYS):
        v = input.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None
