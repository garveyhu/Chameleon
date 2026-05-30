"""验证 LangChain-native 检索埋点：KbRetriever.search() → BaseRetriever 原生
on_retriever_start/end 回调 → CallLogCallbackHandler 落 retriever 行。

证明组件继承 LangChain 基类即「白嫖钩子」，retriever 业务里零 trace 代码。
"""

from __future__ import annotations

import pytest
from langchain_core.callbacks import AsyncCallbackManagerForRetrieverRun
from langchain_core.documents import Document

from chameleon.core.observe.context import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.core.observe.sink import set_observation_sink
from chameleon.integrations.retrievers import KbRetriever


@pytest.fixture
def captured(monkeypatch):
    rows: list[dict] = []

    async def fake_sink(session, **fields):
        rows.append(fields)

    set_observation_sink(fake_sink)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    import chameleon.data.infra.db as db_mod

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", lambda: _FakeSession())
    yield rows
    set_observation_sink(None)


class _FakeKbRetriever(KbRetriever):
    """绕过 DB/embedding，直接返假 Document（钩子流程不变）。"""

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        del run_manager, query
        return [
            Document(
                page_content="向量检索命中的内容",
                metadata={
                    "source": "kb1",
                    "ref": "doc1#0",
                    "score": 0.91,
                    "_hit": {
                        "id": 1,
                        "doc_id": 1,
                        "seq": 0,
                        "content": "向量检索命中的内容",
                        "score": 0.91,
                    },
                },
            )
        ]


async def test_kb_retriever_native_callback_records_retriever(captured):
    token = set_trace_context(
        TraceContext(request_id="req-1", channel="api", app_id="app-x", agent_key="ag-x")
    )
    try:
        retriever = _FakeKbRetriever(kb_key="kb1", top_k=3)
        hits = await retriever.search("我的问题")
    finally:
        reset_trace_context(token)

    # 业务侧仍拿到 ChunkHit
    assert len(hits) == 1
    assert hits[0].content == "向量检索命中的内容"
    assert hits[0].score == 0.91

    # 回调自动落了一条 retriever 行（业务零 trace 代码）
    retriever_rows = [r for r in captured if r["observation_type"] == "retriever"]
    assert len(retriever_rows) == 1
    row = retriever_rows[0]
    assert row["app_id"] == "app-x"
    assert row["agent_key"] == "ag-x"
    assert row["channel"] == "api"
    assert row["success"] is True
    assert row["response_payload"]["hit_count"] == 1
    assert row["response_payload"]["citations"][0]["source"] == "kb1"
    assert row["response_payload"]["citations"][0]["score"] == 0.91
    assert row["duration_ms"] >= 0
