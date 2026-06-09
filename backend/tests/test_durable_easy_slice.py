"""durable 覆盖「易」片真库往返（T1-2）：kb.search / media.generate / complete(schema=)。

每类：首跑经 transport 真调 1 次 + journal 落 AgentMemory（真 test-DB）；重放（同 run_id、
fresh AgentRun，模拟 resume/崩溃恢复）按 call_index 返记录值、**transport 零再调**、还原成活
对象（Doc 列表 / MediaResult / pydantic 实例）。这是 durable 重放零重复计费/副作用的核心契约。

不 mock DB（journal 走真 AgentMemory）；被 journal 的外部调用用计数 fake 注入（验是否重调）。
参照 tests/test_durable_hitl_scope.py 的真库往返范式。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import delete

from chameleon.agentkit import AgentRun
from chameleon.agentkit._spec import Doc, MediaResult
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory
from chameleon.providers.local.agentkit_runner import InProcessTransport

_AGENT = "_t_durable_easy"


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


def _durable_run(run_id: str) -> AgentRun:
    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref="user-A")
    return AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id="user-A", config={}, durable=True, run_id=run_id,
    )


@pytest.mark.asyncio
async def test_kb_search_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    calls = {"n": 0}

    async def fake_kb_search(self, query, **kw):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return [Doc(text=f"hit-{query}", score=0.8, source="kb#1", metadata={"q": query})]

    monkeypatch.setattr(InProcessTransport, "kb_search", fake_kb_search)

    rid = "rid-kb-1"
    run1 = _durable_run(rid)
    docs1 = await run1.kb.search("北京天气")
    assert calls["n"] == 1
    assert docs1[0].text == "hit-北京天气" and docs1[0].source == "kb#1"

    # 重放：同 run_id 新 AgentRun（call_index 重置 0）→ 命中 journal[0]，transport 零再调
    run2 = _durable_run(rid)
    docs2 = await run2.kb.search("北京天气")
    assert calls["n"] == 1, "重放不应重跑检索"
    assert isinstance(docs2[0], Doc)
    assert docs2[0].text == "hit-北京天气" and docs2[0].metadata == {"q": "北京天气"}
    await _clean()


@pytest.mark.asyncio
async def test_media_generate_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    calls = {"n": 0}

    async def fake_media(self, *, kind, prompt, slot=None, model=None, params=None, input_images=None):  # noqa: ANN001, ANN202
        calls["n"] += 1
        return MediaResult(
            url=f"http://minio/{prompt}.png", object_key=f"{prompt}.png",
            media_kind=kind, mime_type="image/png", filename=f"{prompt}.png",
        )

    monkeypatch.setattr(InProcessTransport, "media_generate", fake_media)

    rid = "rid-media-1"
    run1 = _durable_run(rid)
    m1 = await run1.media.generate(kind="image", prompt="cat")
    assert calls["n"] == 1 and m1.url == "http://minio/cat.png"

    run2 = _durable_run(rid)
    m2 = await run2.media.generate(kind="image", prompt="cat")
    assert calls["n"] == 1, "重放不应重出图/重扣费"
    assert isinstance(m2, MediaResult)
    assert m2.url == "http://minio/cat.png" and m2.media_kind == "image"
    await _clean()


class _Sentiment(BaseModel):
    label: str
    score: float


@pytest.mark.asyncio
async def test_complete_schema_journaled_and_replayed(monkeypatch) -> None:
    await _clean()
    calls = {"n": 0}

    class _FakeStructured:
        async def ainvoke(self, messages, **kw):  # noqa: ANN001
            calls["n"] += 1
            return _Sentiment(label="positive", score=0.95)

    monkeypatch.setattr(
        InProcessTransport, "structured_model",
        lambda self, *, slot=None, model=None, schema=None: _FakeStructured(),
    )

    rid = "rid-schema-1"
    run1 = _durable_run(rid)
    r1 = await run1.complete(user="评价", schema=_Sentiment)
    assert calls["n"] == 1 and isinstance(r1, _Sentiment) and r1.label == "positive"

    run2 = _durable_run(rid)
    r2 = await run2.complete(user="评价", schema=_Sentiment)
    assert calls["n"] == 1, "重放不应重调结构化模型"
    assert isinstance(r2, _Sentiment), "重放应 model_validate 还原成 pydantic 实例"
    assert r2.label == "positive" and r2.score == 0.95
    await _clean()


@pytest.mark.asyncio
async def test_replay_fingerprint_mismatch_raises(monkeypatch) -> None:
    """重放时换了入参（指纹不符）→ 报错而非静默返旧值（控制流非确定性防护）。"""
    await _clean()

    async def fake_kb_search(self, query, **kw):  # noqa: ANN001, ANN202
        return [Doc(text="x", score=0.5)]

    monkeypatch.setattr(InProcessTransport, "kb_search", fake_kb_search)
    rid = "rid-fp-1"
    await (_durable_run(rid)).kb.search("query-A")
    with pytest.raises(RuntimeError, match="非确定性|不符"):
        await (_durable_run(rid)).kb.search("query-B-changed")  # 同 idx 不同指纹
    await _clean()
