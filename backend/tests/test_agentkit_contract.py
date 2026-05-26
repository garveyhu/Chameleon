"""agentkit 公共面契约测试（Phase 0）。

只验证公共 API 形状与声明捕获；不触运行时实现（shells 应 raise NotImplementedError）。
"""

import pytest

from chameleon.agentkit import (
    AgentManifest,
    AgentRun,
    BaseAgent,
    Doc,
    ModelSlot,
    Opt,
    agent,
    declared_agents,
)


def test_agent_decorator_captures_function_manifest():
    @agent(
        key="ut-faq",
        name="单测 FAQ",
        models=[ModelSlot("chat", "对话模型", default="qwen-plus"), ModelSlot("fast", "小模型", optional=True)],
        kb=True,
        config=[Opt("tone", "语气", choices=["专业", "活泼"], default="专业")],
        tags=["ut"],
    )
    async def handle(ctx: AgentRun) -> str:
        return ""

    m: AgentManifest = handle.__agent_manifest__
    assert m.key == "ut-faq"
    assert [s.name for s in m.models] == ["chat", "fast"]
    assert m.models[1].optional is True
    assert m.kb is True
    assert [o.key for o in m.config] == ["tone"]
    assert m.is_class is False
    assert declared_agents()["ut-faq"] is m


def test_agent_decorator_captures_class_manifest():
    @agent(key="ut-cls", name="类式")
    class MyAgent(BaseAgent):
        @classmethod
        def get_metadata(cls):  # noqa: D102
            ...

    assert MyAgent.__agent_manifest__.is_class is True


def test_duplicate_key_rejected():
    @agent(key="ut-dup", name="一")
    async def a(ctx):  # noqa: ANN001
        ...

    with pytest.raises(ValueError, match="重复声明"):

        @agent(key="ut-dup", name="二")
        async def b(ctx):  # noqa: ANN001
            ...


def test_doc_shape():
    d = Doc(text="hi", score=0.8, source="kb:faq")
    assert d.text == "hi" and d.score == 0.8 and d.metadata == {}


async def test_agentrun_kb_proxy_delegates():
    """ctx.kb.search 转发给 transport（Phase 2）。"""

    class FakeTransport:
        def __init__(self):
            self.calls = []

        async def kb_search(self, query, *, kbs=None, top_k=None, min_score=0.0):
            self.calls.append((query, kbs, top_k))
            return [Doc(text="命中", score=0.9, source="kb:faq#1")]

    t = FakeTransport()
    run = AgentRun(
        transport=t,  # type: ignore[arg-type]
        agent_key="ut",
        query="q",
        messages=[],
        history=[],
        session_id=None,
        config={},
    )
    docs = await run.kb.search("hello", kbs=["faq"], top_k=2)
    assert len(docs) == 1 and docs[0].text == "命中"
    assert t.calls == [("hello", ["faq"], 2)]
