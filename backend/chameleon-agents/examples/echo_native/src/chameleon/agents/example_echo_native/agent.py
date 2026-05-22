"""EchoNativeAgent —— 范式样板：纯 Python async generator

零外部框架依赖（除 chameleon-core + providers-base）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.providers.base.types import InvokeContext, StreamEvent, StreamEventType


class EchoNativeAgent(BaseAgent):
    """纯 Python echo agent —— 不用 LangGraph、不用 LangChain"""

    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="example-echo-native",
            name="Echo (Native)",
            description="纯 Python 异步生成器范式：本地 agent 框架解耦演示",
            version="0.1",
            tags=["builtin", "example", "native"],
        )

    @classmethod
    async def astream(cls, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        """直接 yield StreamEvent，框架不干涉。

        当 agent 在 admin 里挂载 KB 时，retrieve() 返 top_k chunks，
        echo 把命中的来源摘要拼进输出；没挂 KB 时退化为纯回声。
        """
        # 取当前轮文本
        if isinstance(ctx.input, str):
            text = ctx.input
        else:
            text = ctx.input[-1].content if ctx.input else ""

        # 1) step：retrieve
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "retrieve", "status": "running"},
        )

        try:
            hits = await cls.retrieve(ctx, text, top_k=3)
        except Exception:  # noqa: BLE001
            hits = []

        yield StreamEvent(
            type=StreamEventType.step,
            data={
                "name": "retrieve",
                "status": "success",
                "hits": [
                    {"doc_id": h.doc_id, "score": round(h.score, 3)}
                    for h in hits
                ],
            },
        )

        # 2) delta：按字符流出
        if hits:
            context_preview = " · ".join(
                f"#{i + 1} doc:{h.doc_id}#{h.seq}" for i, h in enumerate(hits[:3])
            )
            prefix = f"echo(kb-aware|{context_preview}): "
        else:
            prefix = "echo(native): "
        for ch in prefix + text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": ch})

        # 3) metadata：usage + citations（chunk 命中转成 citation）
        meta_data: dict = {
            "usage": {
                "prompt_tokens": len(text),
                "completion_tokens": len(prefix + text),
                "total_tokens": len(text) + len(prefix + text),
            }
        }
        if hits:
            meta_data["citations"] = [
                {
                    "chunk_id": h.id,
                    "doc_id": h.doc_id,
                    "seq": h.seq,
                    "score": h.score,
                    "content": h.content[:200],
                }
                for h in hits
            ]
        yield StreamEvent(type=StreamEventType.metadata, data=meta_data)
