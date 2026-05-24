"""AI 自动编排（A4）：自然语言描述 → GraphSpec

调默认 LLM，按节点库 + GraphSpec schema 生成一张工作流图 JSON，结构 + 节点 data
校验通过后返回；校验失败把错误喂回模型重试一次。
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.graph import GraphSpec
from chameleon.core.graph.engine import Orchestrator

_SYSTEM_PROMPT = """\
你是工作流编排生成器。根据用户的自然语言描述，输出一张工作流图的 JSON。
只输出 JSON，不要任何解释 / markdown 代码块。

JSON 结构：
{
  "nodes": [{"id": "...", "type": "...", "name": "中文显示名", "data": {...}, "position": {"x": 0, "y": 200}}],
  "edges": [{"id": "e1", "source": "起点id", "target": "终点id", "source_handle": null}]
}

硬规则：
- 必须恰好一个 type="start"（id 用 "start"）和一个 type="end"（id 用 "end"）。
- 节点 id 简短唯一（如 kb1 / llm1 / ans）。position 从 start x=80 起每个 +240，y=200。
- 变量引用：用户本轮问题 = {{#sys.query#}}，对话历史 = {{#sys.history#}}，
  上游节点输出 = {{#节点id.字段#}}（如 {{#kb1.joined_context#}}）。

可用节点类型与 data：
- start / end：data 留空 {}。
- llm：{"system_prompt": "...", "memory_window": 10}。model_name 留空走默认。
  system_prompt 里用 {{#sys.query#}} 拿问题、{{#上游id.字段#}} 拿上下文。
- kb：{"kb_key": "知识库key", "top_k": 5}。输出字段 joined_context / hits / query。
- http：{"method": "GET", "url": "https://...?q={{#sys.query#}}"}。输出 status_code / body / headers。
- if_else：{"condition": {"op": "==", "left": {"var": "字段"}, "right": {"const": 值}}}。
  出两条边，source_handle 分别 "true" / "false"。
- template：{"template": "拼接 {{#...#}} 的文本"}。输出 text。
- aggregator：{"fields": {"ctx": "{{#kb1.joined_context#}}"}}。
- answer：{"answer": "{{#llm1.answer#}}"}。显式标记最终回答来源（聊天类建议用它收尾）。

示例（带知识库的客服 chat agent）：
{"nodes":[
 {"id":"start","type":"start","name":"开始","data":{},"position":{"x":80,"y":200}},
 {"id":"kb1","type":"kb","name":"检索知识库","data":{"kb_key":"smoke","top_k":5},"position":{"x":320,"y":200}},
 {"id":"llm1","type":"llm","name":"生成回答","data":{"system_prompt":"你是客服助理。参考资料：{{#kb1.joined_context#}}\\n请据此回答用户：{{#sys.query#}}","memory_window":10},"position":{"x":560,"y":200}},
 {"id":"ans","type":"answer","name":"回答","data":{"answer":"{{#llm1.answer#}}"},"position":{"x":800,"y":200}},
 {"id":"end","type":"end","name":"结束","data":{},"position":{"x":1040,"y":200}}],
 "edges":[
 {"id":"e1","source":"start","target":"kb1"},
 {"id":"e2","source":"kb1","target":"llm1"},
 {"id":"e3","source":"llm1","target":"ans"},
 {"id":"e4","source":"ans","target":"end"}]}
"""


def _extract_json(text: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON 对象（容忍 ```json 代码块 / 前后噪声）。"""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1)
    else:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end != -1:
            t = t[start : end + 1]
    return json.loads(t)


def _validate(spec_dict: dict[str, Any]) -> GraphSpec:
    """结构 + 节点 data 校验（构 Orchestrator 会触发各节点 validate_data）。"""
    gs = GraphSpec.model_validate(spec_dict)
    Orchestrator(gs)  # 实例化节点 → data 校验；非法 raise
    return gs


async def generate_graph_spec(description: str) -> dict[str, Any]:
    """NL 描述 → 校验通过的 GraphSpec dict。失败把错误喂回重试一次。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from chameleon.core.components.llms.factory import resolve_llm

    client = await resolve_llm(None)
    messages: list[Any] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"描述：{description}\n\n只输出 JSON。"),
    ]

    last_err = ""
    for attempt in range(2):
        ai = await client.ainvoke(messages)
        text = ai.content if hasattr(ai, "content") else str(ai)
        try:
            spec_dict = _extract_json(str(text))
            _validate(spec_dict)
            logger.info("AI 编排生成成功 | attempt={}", attempt + 1)
            return spec_dict
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:300]
            logger.warning("AI 编排生成校验失败（attempt {}）: {}", attempt + 1, last_err)
            messages.append(ai)
            messages.append(
                HumanMessage(
                    content=f"上面的 JSON 校验失败：{last_err}。请修正后只重新输出 JSON。"
                )
            )

    raise BusinessError(
        ResultCode.InternalError,
        message=f"AI 编排生成失败（校验不过）：{last_err}",
    )
