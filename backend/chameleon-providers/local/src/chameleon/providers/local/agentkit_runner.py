"""agentkit @agent 运行适配（Phase 1）。

把 `InvokeContext` 适配成 `AgentRun` + `InProcessTransport`，调作者 `handle(ctx)`，
再把返回（`str` 协程 / `AsyncIterator[str]` 异步生成器）适配成 `StreamEvent` 流。

模型解析全部落到平台「已配置资源池」（LLMFactory 缓存，按 LLMModel.code）：
- slot：该 agent 的绑定链（web 绑定 model_bindings[slot] → 槽 default → 系统默认）
- model：直接点名某已配置 code（= llm_by_name），非法 raise

注：per-request routing/failover（core.routing.resolve_llm）需 DB session，
InvokeContext 不带；Phase 1 沿用缓存工厂（与既有本地 agent 行为一致），后续接入。
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import AsyncIterator
from typing import Any

from chameleon.agentkit import AgentRun, RuntimeTransport
from chameleon.agentkit._spec import Doc, ModelSlot
from chameleon.core.components import llm, llm_by_name, search_kb
from chameleon.core.components.knowledge import list_linked_kb_metas
from chameleon.core.observe.context import observe
from chameleon.providers.base.types import (
    Citation,
    InvokeContext,
    StreamEvent,
    StreamEventType,
)


class InProcessTransport(RuntimeTransport):
    """站内进程内 transport：直连 LLMFactory / KB / observe。"""

    def __init__(
        self,
        *,
        agent_key: str,
        bindings: dict[str, str],
        slots: dict[str, ModelSlot],
    ) -> None:
        self._agent_key = agent_key
        self._bindings = bindings or {}
        self._slots = slots or {}
        self._pending: list[StreamEvent] = []

    def _resolve_code(self, slot: str) -> str | None:
        s = self._slots.get(slot)
        if s is not None and s.locked:
            return s.default
        code = self._bindings.get(slot)
        if code:
            return code
        return s.default if s is not None else None

    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        if model:
            return llm_by_name(model)  # 校验：非已配置即 RegistryError
        if slot:
            code = self._resolve_code(slot)
            if code:
                return llm_by_name(code)
        return llm()  # 系统默认

    async def kb_search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
    ) -> list[Doc]:
        # kbs 给定=代码点名；否则用该 agent web 关联的 KB（agent_kb_link）
        if kbs:
            kb_keys = list(kbs)
        else:
            metas = await list_linked_kb_metas(self._agent_key)
            kb_keys = [m.kb_key for m in metas]
        if not kb_keys:
            return []

        merged = []
        async with observe(observation_type="retrieval", name="kb.search"):
            for kb_key in kb_keys:
                hits = await search_kb(
                    kb_key, query, top_k=top_k, min_score=min_score
                )
                for h in hits:
                    merged.append((kb_key, h))
        merged.sort(key=lambda kh: getattr(kh[1], "score", 0.0), reverse=True)
        merged = merged[: (top_k or 5)]

        docs: list[Doc] = []
        for kb_key, h in merged:
            doc = Doc(
                text=h.content,
                score=h.score,
                source=f"{kb_key}#doc{h.doc_id}#{h.seq}",
                metadata={"kb_key": kb_key, "doc_id": h.doc_id, "seq": h.seq, **(h.meta or {})},
            )
            docs.append(doc)
            # 自动 citation：作者无需手动 yield
            self.emit(
                StreamEvent(
                    type=StreamEventType.citation,
                    data=Citation(
                        source=doc.source,
                        score=h.score,
                        snippet=h.content[:200],
                        meta=doc.metadata,
                    ).model_dump(),
                )
            )
        return docs

    def span(self, name: str, *, type: str = "span") -> Any:
        return observe(observation_type=type, name=name)

    def emit(self, event: StreamEvent) -> None:
        self._pending.append(event)

    def drain(self) -> list[StreamEvent]:
        out, self._pending = self._pending, []
        return out


def _extract_query(ctx: InvokeContext) -> str:
    inp = ctx.input
    if isinstance(inp, str):
        return inp
    for m in reversed(inp):
        if getattr(m, "role", None) == "user":
            return m.text()
    return inp[-1].text() if inp else ""


def is_agentkit_agent(ctx: InvokeContext) -> bool:
    """该 agent 是否走 agentkit（registry build 时注入了定位标记）。"""
    return bool(ctx.agent_def.config.get("__agentkit_module__"))


async def run_agentkit(ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
    """运行一个 @agent 声明的本地智能体，产出 StreamEvent 流。"""
    cfg = ctx.agent_def.config
    mod = importlib.import_module(cfg["__agentkit_module__"])
    target = getattr(mod, cfg["__agentkit_attr__"])
    manifest = target.__agent_manifest__
    slots = {s.name: s for s in manifest.models}

    transport = InProcessTransport(
        agent_key=ctx.agent_def.key,
        bindings=cfg.get("model_bindings") or {},
        slots=slots,
    )
    run = AgentRun(
        transport=transport,
        agent_key=ctx.agent_def.key,
        query=_extract_query(ctx),
        messages=ctx.input if isinstance(ctx.input, list) else [],
        history=ctx.history,
        session_id=ctx.session_id,
        config=cfg.get("opts") or {},
    )

    # 类式 @agent（BaseAgent 子类）：暂走其 astream（高级路径，后续 phase 细化）
    if manifest.is_class:
        async for ev in target.astream(ctx):
            yield ev
        return

    result = target(run)
    if inspect.isasyncgen(result):
        async for chunk in result:
            yield StreamEvent(type=StreamEventType.delta, data={"text": chunk})
            for ev in transport.drain():
                yield ev
    else:
        text = await result
        for ev in transport.drain():
            yield ev
        if text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": text})
