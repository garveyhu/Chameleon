"""NL 描述 → 工作流图 JSON —— AI 自动编排的 AI 内核。

prompt + 双轮校验重试 + trace 收口在此。**图结构校验由调用方注入**（``validate``
回调）——因为图校验依赖 ``engine.graph``，而 aikit 是底层包不能反向依赖，故把
engine 相关逻辑留在调用方（system 层）以回调形式注入。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger

from chameleon.aikit._json import extract_json
from chameleon.aikit.base import LLMRunner

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


class GraphSpecError(RuntimeError):
    """NL→图生成失败（双轮后仍校验不过）。调用方转成业务异常。"""


async def generate_graph_spec(
    description: str,
    *,
    validate: Callable[[dict[str, Any]], None],
    model: str | None = None,
) -> dict[str, Any]:
    """NL 描述 → 校验通过的图 dict。校验失败把错误喂回重试一次。

    Args:
        description: 自然语言工作流描述
        validate: 图校验回调（校验失败 raise）；调用方注入 engine.graph 校验
        model: 生成用 LLM code；None 走系统默认

    Raises:
        GraphSpecError: 双轮后仍校验不过（携带最后一次校验错误）
    """
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    from chameleon.core.observe import TraceContext, open_trace_scope

    messages: list[Any] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"描述：{description}\n\n只输出 JSON。"),
    ]

    last_err = ""
    # 双轮（生成→校验失败喂回修正）共用一个 internal trace，两次 generation 归同一棵树
    async with open_trace_scope(
        TraceContext(request_id=uuid.uuid4().hex, channel="internal")
    ):
        for attempt in range(2):
            text = await LLMRunner.run_text(messages, model=model, retries=0)
            try:
                spec_dict = extract_json(str(text))
                validate(spec_dict)
                logger.info("AI 编排生成成功 | attempt={}", attempt + 1)
                return spec_dict
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:300]
                logger.warning(
                    "AI 编排生成校验失败（attempt {}）: {}", attempt + 1, last_err
                )
                messages.append(AIMessage(content=text))
                messages.append(
                    HumanMessage(
                        content=f"上面的 JSON 校验失败：{last_err}。请修正后只重新输出 JSON。"
                    )
                )

    raise GraphSpecError(last_err)
