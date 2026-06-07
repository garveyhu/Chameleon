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
import json
from collections.abc import AsyncIterator
from typing import Any

from chameleon.agentkit import AgentRun, RuntimeTransport
from chameleon.agentkit._runtime import _content_to_text
from chameleon.agentkit._spec import Doc, ModelSlot, ToolSpec
from chameleon.core.observe.context import (
    ObservationType,
    current_observation_id,
    current_trace_context,
    observe,
)
from chameleon.integrations.components import llm, llm_by_name, search_kb
from chameleon.integrations.knowledge import list_linked_kb_metas
from chameleon.integrations.tools.loop import (
    bind_schemas,
    extract_tool_calls,
    extract_usage,
    merge_usage,
    run_tool_calls,
    tool_schemas,
)
from chameleon.providers.base.types import (
    Citation,
    InvokeContext,
    StreamEvent,
    StreamEventType,
)


def _scoped_observation_id(name: str) -> str | None:
    """把 agentkit span 锚到当前 trace 根，沿用图引擎 `{root}.{seg}` 命名约定。

    GenerationRecorder 落 generation 时取 `current_observation_id()` 当 parent；
    而根行 rollup（aggregate_generation_rollup）只认 `parent_id == root` 或
    `parent_id LIKE 'root.%'`。agentkit 的 `ctx.stream/.complete` 会在 LLM 调用外
    套一层 span，若该 span 用裸 uuid，则其下 generation 的 parent 既不等于根、也不
    以 `root.` 开头 → rollup 漏掉 token/cost/model（评测 agent 路径根行因此全 None）。

    解决：让 span id 以当前 trace 根 request_id 为前缀。已在嵌套 span 内（且该 span
    已是 `root.*` 形态）时挂其下继续延伸；否则直接挂根。无 TraceContext（裸路径）
    返回 None，交回 observe 默认生成 uuid（兜底落 internal，不影响计费正确性）。
    """
    tc = current_trace_context()
    root = tc.request_id if tc else None
    if not root:
        return None
    current = current_observation_id()
    base = current if (current and current.startswith(f"{root}.")) else root
    return f"{base}.{name}"


class InProcessTransport(RuntimeTransport):
    """站内进程内 transport：直连 LLMFactory / KB / observe。"""

    def __init__(
        self,
        *,
        agent_key: str,
        bindings: dict[str, str],
        slots: dict[str, ModelSlot],
        tool_keys: list[str] | None = None,
        request_id: str | None = None,
        session_id: str | None = None,
        a2a_depth: int = 0,
        budget: int = 100_000,
        scope_ref: str | None = None,
    ) -> None:
        self._agent_key = agent_key
        self._bindings = bindings or {}
        self._slots = slots or {}
        #: 该 agent 启用的平台工具 key（manifest.tools ∩ web tool_bindings）
        self._tool_keys = list(tool_keys or [])
        #: A2A 上下文（trace 根 / 当前深度 / 剩余预算）
        self._request_id = request_id
        self._session_id = session_id
        self._a2a_depth = a2a_depth
        self._budget = budget
        #: ctx.memory 作用域（end_user_id 优先，退化 session_id）
        self._scope_ref = scope_ref
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

    def structured_model(
        self, *, slot: str | None = None, model: str | None = None, schema: type
    ) -> Any:
        return self.chat_model(slot=slot, model=model).with_structured_output(schema)

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
        async with observe(
            observation_type="retrieval",
            name="kb.search",
            request_id=_scoped_observation_id("kb.search"),
        ):
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

    async def run_tool_loop(
        self,
        *,
        messages: list[Any],
        slot: str | None,
        model: str | None,
        platform_keys: list[str],
        local_tools: list[ToolSpec],
        max_steps: int,
    ) -> AsyncIterator[str]:
        from langchain_core.messages import ToolMessage

        base = self.chat_model(slot=slot, model=model)

        # 平台工具：该 agent 绑定集 ∪ 本轮临时点名；去重保序
        plat = list(dict.fromkeys([*self._tool_keys, *(platform_keys or [])]))
        schemas = tool_schemas(plat)
        local_by_name = {s.name: s for s in local_tools}
        for s in local_tools:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": s.name,
                        "description": s.description,
                        "parameters": s.parameters_schema,
                    },
                }
            )
        client = bind_schemas(base, schemas) if schemas else base

        tc = current_trace_context()
        related = tc.request_id if tc else None
        convo = list(messages)
        usage: dict[str, int] | None = None

        async with observe(
            observation_type="span",
            name="agent.tools",
            request_id=_scoped_observation_id("agent.tools"),
        ):
            for _step in range(max_steps):
                resp = await client.ainvoke(convo)
                usage = merge_usage(usage, extract_usage(resp))
                calls = extract_tool_calls(resp)
                if not calls:
                    text = _content_to_text(resp)
                    if text:
                        yield text
                    return

                convo.append(resp)  # AIMessage（带 tool_calls）
                for c in calls:
                    self.emit(
                        StreamEvent(
                            type=StreamEventType.tool_call,
                            data={"name": c["name"], "args": c["args"], "id": c["id"]},
                        )
                    )

                plat_calls = [c for c in calls if c["name"] not in local_by_name]
                loc_calls = [c for c in calls if c["name"] in local_by_name]
                tool_msgs: list[Any] = []

                if plat_calls:
                    msgs, records = await run_tool_calls(
                        plat_calls,
                        caller="agentkit",
                        related_id=related,
                        extra={"agent_key": self._agent_key},
                    )
                    tool_msgs.extend(msgs)
                    for r in records:
                        self.emit(
                            StreamEvent(
                                type=StreamEventType.tool_result,
                                data={"name": r["name"], "id": r["id"], "result": r["result"]},
                            )
                        )

                for c in loc_calls:
                    spec = local_by_name[c["name"]]
                    result = await self._exec_local(spec, c["args"])
                    tool_msgs.append(
                        ToolMessage(
                            content=json.dumps(result, ensure_ascii=False, default=str),
                            tool_call_id=c["id"] or c["name"],
                        )
                    )
                    self.emit(
                        StreamEvent(
                            type=StreamEventType.tool_result,
                            data={"name": c["name"], "id": c["id"], "result": result},
                        )
                    )

                convo.extend(tool_msgs)

            # 达轮次上限：标记 + 最后一次无强制工具的收口回答
            self.emit(
                StreamEvent(
                    type=StreamEventType.step,
                    data={
                        "name": "tool-loop",
                        "status": "success",
                        "output": {"note": f"工具循环达上限 {max_steps} 轮，强制收口"},
                    },
                )
            )
            final = await client.ainvoke(convo)
            text = _content_to_text(final)
            if text:
                yield text

    async def _exec_local(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        """执行作者本地 @tool，落 TOOL 观测，异常收敛成 ok=False。"""
        async with observe(
            observation_type=ObservationType.TOOL,
            name=spec.name,
            request_id=_scoped_observation_id(spec.name),
        ):
            try:
                data = await spec.handler(**(args or {}))
                return {"tool_key": spec.name, "ok": True, "data": data, "error": None}
            except Exception as e:  # noqa: BLE001
                return {
                    "tool_key": spec.name,
                    "ok": False,
                    "data": None,
                    "error": f"{type(e).__name__}: {str(e)[:300]}",
                }

    async def memory_get(self, key: str, default: Any = None) -> Any:
        if not self._scope_ref:
            return default
        from sqlalchemy import select

        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import AgentMemory

        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    select(AgentMemory).where(
                        AgentMemory.agent_key == self._agent_key,
                        AgentMemory.scope_ref == self._scope_ref,
                        AgentMemory.mkey == key,
                    )
                )
            ).scalar_one_or_none()
        if row is None or not isinstance(row.value, dict):
            return default
        return row.value.get("v", default)

    async def memory_set(self, key: str, value: Any) -> None:
        if not self._scope_ref:
            return
        from sqlalchemy import select

        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import AgentMemory

        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    select(AgentMemory).where(
                        AgentMemory.agent_key == self._agent_key,
                        AgentMemory.scope_ref == self._scope_ref,
                        AgentMemory.mkey == key,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                s.add(
                    AgentMemory(
                        agent_key=self._agent_key,
                        scope_ref=self._scope_ref,
                        mkey=key,
                        value={"v": value},
                    )
                )
            else:
                row.value = {"v": value}
            await s.commit()

    async def memory_all(self) -> dict[str, Any]:
        if not self._scope_ref:
            return {}
        from sqlalchemy import select

        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import AgentMemory

        async with AsyncSessionLocal() as s:
            rows = (
                await s.execute(
                    select(AgentMemory).where(
                        AgentMemory.agent_key == self._agent_key,
                        AgentMemory.scope_ref == self._scope_ref,
                    )
                )
            ).scalars().all()
        return {
            r.mkey: (r.value.get("v") if isinstance(r.value, dict) else None)
            for r in rows
        }

    async def call_agent(self, target: str, *, input: str) -> str:
        from chameleon.providers.base.a2a_bridge import get_a2a_caller

        caller = get_a2a_caller()
        if caller is None:
            raise RuntimeError(
                "A2A caller 未注入（app 启动应调 engine.agent.a2a.wire_a2a_bridge）"
            )
        tc = current_trace_context()
        # trace 根优先；无 trace 上下文时兜底到 session_id（仍保证 a2a 的 trace_id 非空红线）
        trace_id = self._request_id or (tc.request_id if tc else None) or self._session_id
        if not trace_id:
            raise RuntimeError("ctx.call_agent 需要 trace_id / session_id 至少其一")
        self.emit(
            StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": f"调用子智能体 {target}",
                    "status": "success",
                    "output": {"target": target},
                },
            )
        )
        out = await caller(
            source=self._agent_key,
            target=target,
            input=input,
            trace_id=trace_id,
            budget_remaining=self._budget,
            depth=self._a2a_depth + 1,
        )
        return out.get("answer") or ""

    def span(self, name: str, *, type: str = "span") -> Any:
        return observe(
            observation_type=type,
            name=name,
            request_id=_scoped_observation_id(name),
        )

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

    # 平台工具启用集：manifest 声明的可用集 ∩ web tool_bindings（None=全启用）
    declared_tools = list(manifest.tools or [])
    bindings_cfg = cfg.get("tool_bindings")
    if bindings_cfg is None:
        enabled_tools = declared_tools
    else:
        allowed = set(bindings_cfg)
        enabled_tools = [t for t in declared_tools if t in allowed]

    cvars = ctx.context_vars or {}
    transport = InProcessTransport(
        agent_key=ctx.agent_def.key,
        bindings=cfg.get("model_bindings") or {},
        slots=slots,
        tool_keys=enabled_tools,
        request_id=ctx.request_id,
        session_id=ctx.session_id,
        a2a_depth=int(cvars.get("_a2a_depth", 0)),
        budget=int(cvars.get("_a2a_budget", 100_000)),
        scope_ref=cvars.get("end_user_id") or ctx.session_id,
    )
    run = AgentRun(
        transport=transport,
        agent_key=ctx.agent_def.key,
        query=_extract_query(ctx),
        messages=ctx.input if isinstance(ctx.input, list) else [],
        history=ctx.history,
        session_id=ctx.session_id,
        config=cfg.get("opts") or {},
        attachments=ctx.attachments,
    )

    if manifest.is_class:
        # 新式类：定义了实例方法 handle(self, run) → 注入 AgentRun + transport，
        # 与函数式共用同一 ctx（兑现「两层共用同一 ctx」）。
        if hasattr(target, "handle"):
            inst = target()
            async for ev in _consume(inst.handle(run), transport):
                yield ev
            return
        # 旧式兼容：classmethod astream(ctx)（裸 InvokeContext，不享 ctx 便利）
        async for ev in target.astream(ctx):
            yield ev
        return

    async for ev in _consume(target(run), transport):
        yield ev


async def _consume(
    result: Any, transport: InProcessTransport
) -> AsyncIterator[StreamEvent]:
    """把作者 handler 返回（async generator / coroutine）适配成 StreamEvent 流。

    每个文本增量前先 drain transport 缓冲（tool_call/tool_result/citation/step），
    保证工具调用 / 引用出现在对应答案文本之前。
    """
    if inspect.isasyncgen(result):
        async for chunk in result:
            for ev in transport.drain():
                yield ev
            yield StreamEvent(type=StreamEventType.delta, data={"text": chunk})
        for ev in transport.drain():
            yield ev
    else:
        text = await result
        for ev in transport.drain():
            yield ev
        if text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": text})
