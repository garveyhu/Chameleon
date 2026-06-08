"""真客户端端到端：真 langchain_openai.ChatOpenAI 经真 httpx 请求 → respx 拦截返 OpenAI 格式
canned 响应。演练真实 SDK 集成链路（请求构建/鉴权头/响应解析）+ StandaloneTransport + ctx.gather
+ 本地子 agent + ctx.complete，仅 LLM 文本是 canned——比鸭子假模型真实得多，闭合"无真实 e2e"门槛。

需 respx + langchain-openai（均已装）；不连任何真 LLM，零 API 花费。
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone


@agent(key="e2e-pros", name="正方", models=[ModelSlot("chat", "对话")])
async def _pros(ctx: AgentRun):
    yield await ctx.complete(system="你是正方，列支持理由。", user=ctx.query)


@agent(key="e2e-cons", name="反方", models=[ModelSlot("chat", "对话")])
async def _cons(ctx: AgentRun):
    yield await ctx.complete(system="你是反方，列反对理由。", user=ctx.query)


@agent(key="e2e-host", name="主持", models=[ModelSlot("chat", "对话")],
       call_agents=["e2e-pros", "e2e-cons"])
async def _host(ctx: AgentRun):
    pro, con = await ctx.gather([("e2e-pros", ctx.query), ("e2e-cons", ctx.query)])
    yield f"正方[{pro}] 反方[{con}]"


def _openai_completion(content: str) -> dict:
    return {
        "id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }


@pytest.mark.asyncio
async def test_real_chatopenai_client_e2e_orchestration():
    """真 ChatOpenAI 客户端 + StandaloneTransport + ctx.gather + 子 agent 全链路（respx 拦 LLM）。"""
    from langchain_openai import ChatOpenAI

    def _responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sys_text = " ".join(m["content"] for m in body["messages"] if m["role"] == "system")
        content = "支持X" if "正方" in sys_text else "反对Y" if "反方" in sys_text else "?"
        return httpx.Response(200, json=_openai_completion(content))

    with respx.mock:
        respx.post(url__regex=r".*/chat/completions").mock(side_effect=_responder)
        model = ChatOpenAI(model="gpt-4o-mini", api_key="sk-test", temperature=0)
        t = StandaloneTransport(model=model, agents={"e2e-pros": _pros, "e2e-cons": _cons})
        out = await run_standalone(_host, "公司是否该全面远程办公", transport=t)

    # 真客户端往返 + 并行扇出 + 两个子 agent 的 complete 都真打到（canned）→ 综合
    assert "支持X" in out and "反对Y" in out
    assert out.startswith("正方[支持X]")


@pytest.mark.asyncio
async def test_real_chatopenai_client_e2e_single_complete():
    """最小真客户端往返：单 agent ctx.complete → 真 ChatOpenAI → respx canned。"""
    from langchain_openai import ChatOpenAI

    @agent(key="e2e-solo", name="solo", models=[ModelSlot("chat", "对话")])
    async def solo(ctx: AgentRun):
        yield await ctx.complete(system="助手", user=ctx.query)

    with respx.mock:
        respx.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=_openai_completion("真实往返答案"))
        )
        model = ChatOpenAI(model="gpt-4o-mini", api_key="sk-test")
        t = StandaloneTransport(model=model)
        out = await run_standalone(solo, "你好", transport=t)

    assert out == "真实往返答案"


def _openai_sse(chunks: list[str]) -> bytes:
    """OpenAI chat.completion 流式 SSE 字节（delta 增量 + [DONE]）。"""
    lines = []
    for c in chunks:
        payload = {"choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


@pytest.mark.asyncio
async def test_real_chatopenai_client_e2e_streaming():
    """真 ChatOpenAI 流式客户端 e2e：ctx.stream → astream → SSE 解析（RAG 示例用的流式路径）。"""
    from langchain_openai import ChatOpenAI

    @agent(key="e2e-stream", name="s", models=[ModelSlot("chat", "对话")])
    async def streamer(ctx: AgentRun):
        async for delta in ctx.stream(system="助手", user=ctx.query):
            yield delta

    with respx.mock:
        respx.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=_openai_sse(["你", "好", "世界"]),
                headers={"content-type": "text/event-stream"},
            )
        )
        model = ChatOpenAI(model="gpt-4o-mini", api_key="sk-test")
        out = await run_standalone(streamer, "hi", transport=StandaloneTransport(model=model))

    # 真客户端解析 SSE 增量 → ctx.stream 逐块 yield → 拼成完整答案
    assert out == "你好世界"
