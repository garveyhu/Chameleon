"""脱平台 RAG 示例 —— `pip install chameleon-agentkit langchain-openai` 后直接 `python` 跑。

演示用 agentkit 在**任意环境、不连 Chameleon 平台**写一个"对我的文档问答"的 RAG 智能体：
检索本地知识库 → 把命中文档作为上下文喂给模型 → 流式作答。同一份 `handle` 代码提交到平台
后走 InProcessTransport（KB 自动接平台 hybrid 检索 + trace + 计费），零改动。

运行（需自带 OpenAI key，或把 ChatOpenAI 换成任意 LangChain chat model）：
    export OPENAI_API_KEY=sk-...
    python standalone_rag.py
"""

from __future__ import annotations

import asyncio

from chameleon.agentkit import AgentRun, Doc, ModelSlot, agent
from chameleon.agentkit.standalone import StandaloneTransport, run_standalone


@agent(
    key="my-docs-qa",
    name="文档问答助手",
    description="基于知识库回答问题，无命中则明说不知道",
    kb=True,
    models=[ModelSlot("chat", "对话模型")],
)
async def handle(ctx: AgentRun):
    docs = await ctx.kb.search(ctx.query, top_k=3)
    if not docs:
        yield "知识库里没有相关内容，我无法回答。"
        return
    context = "\n---\n".join(d.text for d in docs)
    async for delta in ctx.stream(
        system="你是文档问答助手。只依据提供的资料作答，资料没有就说不知道，不要编造。",
        user=ctx.query,
        context=context,  # 检索到的文档作为上下文（ctx 自动拼进 user 消息）
    ):
        yield delta


# 我的本地知识库（平台上是配置好的 KB；standalone 直接传 Doc 列表）
MY_DOCS = [
    Doc(text="Chameleon 的 agentkit 让作者只写 handle(ctx)，模型/知识库/工具/追踪由 ctx 隐式提供。"),
    Doc(text="StandaloneTransport 让 agent 脱平台运行：pip install 后自带模型 key 即可跑。"),
    Doc(text="同一份 handle 代码，换 transport 即换运行环境——本地、dev、平台行为一致。"),
]


async def main() -> None:
    # 把 ChatOpenAI 换成任意 LangChain chat model（本地 Ollama/vLLM 也行，base_url 指过去即可）
    from langchain_openai import ChatOpenAI

    transport = StandaloneTransport(
        model=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        kb_docs=MY_DOCS,
    )
    answer = await run_standalone(handle, "agentkit 怎么脱平台跑？", transport=transport)
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
