"""KbRetriever —— LangChain BaseRetriever 包 KB 向量检索。

`.ainvoke(query)` 时 BaseRetriever **原生 fire** on_retriever_start / on_retriever_end
（出错 fire on_retriever_error）→ 注册的 CallLogCallbackHandler 自动落 retriever trace
节点。本类只实现「取相关文档」，**零 trace 代码**——钩子流程由 LangChain 基类提供。

设计：复用 LangChain 回调总线（方案 A）。和 LLM（BaseChatModel + GenerationRecorder）
同一套机制、同一个 handler、同一棵 trace 树。
"""

from __future__ import annotations

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from chameleon.core.vector import ChunkHit
from chameleon.integrations.components import inventory
from chameleon.integrations.embedding import get_embedding_client
from chameleon.integrations.vector import get_store


class KbRetriever(BaseRetriever):
    """对单个 KB 的向量检索；通过 LangChain 回调自动出 retriever 节点。"""

    kb_key: str
    top_k: int | None = None
    min_score: float = 0.0

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        # 检索是 async（DB）—— 本类只支持 .ainvoke() / .search()
        raise NotImplementedError("KbRetriever 仅支持异步检索：用 .ainvoke() 或 .search()")

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        del run_manager
        # lazy import 破环（knowledge.search_kb → retrievers → knowledge）
        from chameleon.integrations.knowledge import (
            KnowledgeBaseNotFoundError,
            get_kb_meta,
        )

        meta = await get_kb_meta(self.kb_key)
        if meta is None:
            raise KnowledgeBaseNotFoundError(message=f"知识库不存在: {self.kb_key}")

        k = self.top_k or inventory.kb_default_top_k()
        client = get_embedding_client(meta.embedding_model)
        vecs = await client.embed([query])
        if not vecs:
            return []

        hits = await get_store().search(
            kb_id=meta.id,
            query_vec=vecs[0],
            top_k=k,
            min_score=self.min_score,
        )
        return [
            Document(
                page_content=h.content,
                metadata={
                    "source": self.kb_key,
                    "ref": f"doc{h.doc_id}#{h.seq}",
                    "score": round(h.score, 4),
                    # 完整 ChunkHit 回程用（业务侧仍要 ChunkHit）
                    "_hit": h.model_dump(),
                },
            )
            for h in hits
        ]

    async def search(self, query: str) -> list[ChunkHit]:
        """业务侧便利：返回 list[ChunkHit]（内部 .ainvoke 触发回调埋点）。"""
        from chameleon.integrations.observe import get_calllog_handler

        docs = await self.ainvoke(query, config={"callbacks": [get_calllog_handler()]})
        return [ChunkHit.model_validate(d.metadata["_hit"]) for d in docs]


def get_kb_retriever(
    kb_key: str, *, top_k: int | None = None, min_score: float = 0.0
) -> KbRetriever:
    """构造一个 KB retriever（带回调埋点）。"""
    return KbRetriever(kb_key=kb_key, top_k=top_k, min_score=min_score)
