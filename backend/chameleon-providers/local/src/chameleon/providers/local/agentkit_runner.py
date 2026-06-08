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

from loguru import logger

from chameleon.agentkit import AgentRun, RuntimeTransport
from chameleon.agentkit._runtime import _content_to_text
from chameleon.agentkit._spec import Doc, MediaResult, ModelSlot, ToolSpec
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
        mcp_tools: list[ToolSpec] | None = None,
    ) -> None:
        self._agent_key = agent_key
        self._bindings = bindings or {}
        self._slots = slots or {}
        #: 该 agent 启用的平台工具 key（manifest.tools ∩ web tool_bindings）
        self._tool_keys = list(tool_keys or [])
        #: 外部 MCP server 工具（已适配成 ToolSpec），自动并入 run_tool_loop 本地工具
        self._mcp_tools = list(mcp_tools or [])
        #: A2A 上下文（trace 根 / 当前深度 / 剩余预算）
        self._request_id = request_id
        self._session_id = session_id
        self._a2a_depth = a2a_depth
        self._budget = budget
        #: ctx.memory 作用域（end_user_id 优先，退化 session_id）
        self._scope_ref = scope_ref
        #: 本次运行累计 token 用量（complete/stream/工具循环/子调用共账）；run_agentkit
        #: 流末 emit → InvokeResult.usage 非空 → A2A budget_consumed 真实
        self._usage_total: dict[str, int] = {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        }
        self._pending: list[StreamEvent] = []

    def track_usage(self, usage: dict[str, int] | None) -> None:
        if not usage:
            return
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self._usage_total[k] += int(usage.get(k) or 0)

    def usage_total(self) -> dict[str, int]:
        return dict(self._usage_total)

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

    async def media_generate(
        self,
        *,
        kind: str,
        prompt: str,
        slot: str | None = None,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        input_images: list[str] | None = None,
    ) -> MediaResult:
        from sqlalchemy import select

        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import LLMModel
        from chameleon.integrations.mediagen.resolver import resolve_media_target
        from chameleon.integrations.mediagen.service import stream_generate
        from chameleon.integrations.observe.aspect import record_scope
        from chameleon.providers.base.media_cost_bridge import get_media_cost_fn

        # 解析生成模型 code：model 点名优先，否则走 slot 绑定链
        code = model or (self._resolve_code(slot) if slot else None)
        if not code:
            raise RuntimeError(
                "ctx.media.generate 需要 model= 点名或绑定了 image/video 模型的 slot"
            )
        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(select(LLMModel).where(LLMModel.code == code))
            ).scalar_one_or_none()
        if row is None:
            raise RuntimeError(f"生成模型不存在或未配置：{code}")
        target = await resolve_media_target(row.id)
        if kind and target.media_kind and kind != target.media_kind:
            raise RuntimeError(
                f"请求 kind={kind} 与模型 {code} 的类型 {target.media_kind} 不符"
            )

        done: dict[str, Any] | None = None
        # record_scope 落一条 generation 计费行（cost rollup 计入根行）；媒体按张/秒计费，
        # 经 media_cost_bridge 算金额直接写 scope.cost_usd（无 token，不走 token 价）。
        async with record_scope(
            observation_type="generation",
            name=f"media.{kind}",
            request_payload={"kind": kind, "prompt": prompt[:500]},
            model_code=code,
        ) as scope:
            async for ev in stream_generate(
                target, prompt=prompt, params=params or {}, input_images=input_images or []
            ):
                etype = ev.get("type")
                if etype == "progress":
                    self.emit(
                        StreamEvent(
                            type=StreamEventType.step,
                            data={
                                "name": f"media.{kind}",
                                "status": "running",
                                "output": {"elapsed_ms": ev.get("elapsed_ms")},
                            },
                        )
                    )
                elif etype == "done":
                    done = ev
            if not done:
                raise RuntimeError("媒体生成未返回 done 事件")
            scope.response_payload = {"url": done.get("url"), "media_kind": done.get("media_kind")}
            # 计费归集（失败不阻断生成，但在 call_log 标记，避免静默 $0 漏计）
            cost_fn = get_media_cost_fn()
            if cost_fn:
                try:
                    scope.cost_usd = await cost_fn(code, kind, params or {})
                    if scope.cost_usd is None:
                        scope.response_payload["billing_status"] = "no_price"  # 模型无价目
                except Exception:  # noqa: BLE001
                    logger.warning("media 计费失败 model={} kind={}", code, kind)
                    scope.response_payload["billing_status"] = "failed"
        result = MediaResult(
            url=done.get("url", ""),
            object_key=done.get("key", ""),
            media_kind=done.get("media_kind", kind),
            mime_type=done.get("mime_type"),
            filename=done.get("filename"),
        )
        # 产物自动 emit（同 citation 模式，作者无需手动 yield）
        self.emit(
            StreamEvent(
                type=StreamEventType.metadata,
                data={
                    "kind": "media",
                    "media_kind": result.media_kind,
                    "url": result.url,
                    "object_key": result.object_key,
                    "mime_type": result.mime_type,
                    "filename": result.filename,
                },
            )
        )
        return result

    async def kb_search(
        self,
        query: str,
        *,
        kbs: list[str] | None = None,
        top_k: int | None = None,
        min_score: float = 0.0,
        mode: str | None = None,
        rerank: bool | None = None,
        expand: int = 0,
        hyde: bool = False,
    ) -> list[Doc]:
        # kbs 给定=代码点名；否则用该 agent web 关联的 KB（agent_kb_link）
        if kbs:
            kb_keys = list(kbs)
        else:
            metas = await list_linked_kb_metas(self._agent_key)
            kb_keys = [m.kb_key for m in metas]
        if not kb_keys:
            return []

        # 高级检索桥（hybrid/rerank/multi-query/HyDE）；未接桥或未要求高级参数时回退基础向量
        from chameleon.providers.base.retrieval_bridge import get_retrieve_fn

        retrieve_fn = get_retrieve_fn()
        use_advanced = retrieve_fn is not None and (
            mode is not None or rerank is not None or expand or hyde
        )

        # 归一成 (kb_key, content, score, doc_id, seq, meta)
        merged: list[tuple[str, str, float, int, int, dict]] = []
        async with observe(
            observation_type="retrieval",
            name="kb.search",
            request_id=_scoped_observation_id("kb.search"),
        ):
            for kb_key in kb_keys:
                if use_advanced:
                    rows = await retrieve_fn(  # type: ignore[misc]
                        kb_key, query, top_k=top_k, min_score=min_score,
                        mode=mode, rerank=rerank, expand=expand, hyde=hyde,
                    )
                    for r in rows:
                        merged.append((
                            kb_key, r.get("content", ""), r.get("score", 0.0),
                            r.get("doc_id", 0), r.get("seq", 0), r.get("meta") or {},
                        ))
                else:
                    hits = await search_kb(
                        kb_key, query, top_k=top_k, min_score=min_score
                    )
                    for h in hits:
                        merged.append((
                            kb_key, h.content, h.score, h.doc_id, h.seq, h.meta or {}
                        ))
        merged.sort(key=lambda r: r[2], reverse=True)
        merged = merged[: (top_k or 5)]

        docs: list[Doc] = []
        for kb_key, content, score, doc_id, seq, meta in merged:
            doc = Doc(
                text=content,
                score=score,
                source=f"{kb_key}#doc{doc_id}#{seq}",
                metadata={"kb_key": kb_key, "doc_id": doc_id, "seq": seq, **meta},
            )
            docs.append(doc)
            # 自动 citation：作者无需手动 yield
            self.emit(
                StreamEvent(
                    type=StreamEventType.citation,
                    data=Citation(
                        source=doc.source,
                        score=score,
                        snippet=content[:200],
                        meta=doc.metadata,
                    ).model_dump(),
                )
            )
        return docs

    def _charge(self, tokens: int | None) -> None:
        """从该 agent 的剩余 token 预算扣减（统一成本闸：A2A + 工具循环共账）。"""
        if tokens:
            self._budget = max(0, self._budget - int(tokens))

    async def run_tool_loop(
        self,
        *,
        messages: list[Any],
        slot: str | None,
        model: str | None,
        platform_keys: list[str],
        local_tools: list[ToolSpec],
        max_steps: int,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        from langchain_core.messages import ToolMessage

        base = self.chat_model(slot=slot, model=model)

        # 平台工具：该 agent 绑定集 ∪ 本轮临时点名；去重保序
        plat = list(dict.fromkeys([*self._tool_keys, *(platform_keys or [])]))
        schemas = tool_schemas(plat)
        # 本地工具 = 作者传入 + 该 agent 声明的 MCP server 工具（自动并入）
        local_tools = [*local_tools, *self._mcp_tools]
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
        truncate_reason = f"工具循环达上限 {max_steps} 轮"

        async with observe(
            observation_type="span",
            name="agent.tools",
            request_id=_scoped_observation_id("agent.tools"),
        ):
            for _step in range(max_steps):
                resp = await client.ainvoke(convo)
                round_usage = extract_usage(resp)
                if not (round_usage or {}).get("total_tokens"):
                    # 模型未透出 usage → 成本闸本轮静默不咬（流式/部分模型已知现象），记 debug
                    logger.debug(
                        "tool-loop 本轮无 usage，成本闸未计费 agent={}", self._agent_key
                    )
                usage = merge_usage(usage, round_usage)
                self._charge((round_usage or {}).get("total_tokens", 0))  # 计入成本闸
                self.track_usage(round_usage)  # 计入本次运行 usage（供 A2A 上报）
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

                # 成本闸：agent token 预算耗尽 / 本轮循环累计超 max_tokens → 截断收口
                loop_total = (usage or {}).get("total_tokens", 0)
                if self._budget <= 0:
                    truncate_reason = "agent token 预算耗尽"
                    break
                if max_tokens and loop_total >= max_tokens:
                    truncate_reason = f"工具循环 token 超上限 {max_tokens}"
                    break

            # 截断收口：标记 + 最后一次无强制工具的收口回答
            self.emit(
                StreamEvent(
                    type=StreamEventType.step,
                    data={
                        "name": "tool-loop",
                        "status": "success",
                        "output": {"note": f"{truncate_reason}，强制收口"},
                    },
                )
            )
            final = await client.ainvoke(convo)
            final_usage = extract_usage(final)  # 收口这次也计账（评审2：否则截断后超支一次）
            self._charge((final_usage or {}).get("total_tokens", 0))
            self.track_usage(final_usage)
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
        # 成本闸：扣减子智能体实际消耗，扇出多次调用累计受限（不再每次满额放行）
        child_tokens = int(out.get("tokens") or 0)
        self._charge(child_tokens)
        # 子调用消耗计入本 agent 上报 usage（让本 agent 的 A2A 调用方预算也递减，子树共账）
        self.track_usage({"total_tokens": child_tokens})
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


def _resolve_sandbox_policy(agent_key: str, manifest: Any) -> None:
    """沙箱执行决策点 —— Phase 1 fail-closed（T4-2 子方案）。

    `@agent(sandboxed=True)` 表达「该 agent 需隔离执行」（多租户 / 不可信代码）。真隔离
    runtime（handle 进沙箱 + ctx 经受控 RPC 回主进程）见 T4-2 子方案 Phase 2-4，尚未接。
    在此之前：
    - 非生产：进程内跑（开发便利），info 一行。
    - 生产 + sandboxed：**fail-closed**——默认 raise 拒绝进程内裸跑（不可信代码裸跑 =
      读 .env/DB/内网 = RCE，绝不静默假装隔离）。部署方确信源码可信时显式设
      CHAMELEON_SANDBOX_ALLOW_INPROCESS=1 豁免。

    Raises:
        RuntimeError: 生产 + sandboxed + 无真隔离 + 无显式豁免。
    """
    if not getattr(manifest, "sandboxed", False):
        return
    import os

    from chameleon.core.sandbox import is_production

    if not is_production():
        logger.info(
            "agentkit agent {} sandboxed=True（开发态进程内运行；真隔离见 T4-2 子方案）",
            agent_key,
        )
        return
    allow = os.environ.get("CHAMELEON_SANDBOX_ALLOW_INPROCESS", "").strip().lower()
    if allow in ("1", "true", "yes"):
        logger.warning(
            "agentkit agent {} sandboxed=True 按显式豁免进程内运行"
            "（CHAMELEON_SANDBOX_ALLOW_INPROCESS）——确认源码可信",
            agent_key,
        )
        return
    raise RuntimeError(
        f"agent {agent_key} 声明 sandboxed=True，但生产环境未接真隔离 runtime；"
        "fail-closed 拒绝进程内裸跑（防不可信代码 RCE）。接 SandboxTransport（T4-2 子方案）"
        "或显式 CHAMELEON_SANDBOX_ALLOW_INPROCESS=1（确认源码可信）后重试。"
    )


async def run_agentkit(ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
    """运行一个 @agent 声明的本地智能体，产出 StreamEvent 流。"""
    cfg = ctx.agent_def.config
    mod = importlib.import_module(cfg["__agentkit_module__"])
    target = getattr(mod, cfg["__agentkit_attr__"])
    manifest = target.__agent_manifest__
    slots = {s.name: s for s in manifest.models}

    _resolve_sandbox_policy(ctx.agent_def.key, manifest)

    # 平台工具启用集：manifest 声明的可用集 ∩ web tool_bindings（None=全启用）
    declared_tools = list(manifest.tools or [])
    bindings_cfg = cfg.get("tool_bindings")
    if bindings_cfg is None:
        enabled_tools = declared_tools
    else:
        allowed = set(bindings_cfg)
        enabled_tools = [t for t in declared_tools if t in allowed]

    cvars = ctx.context_vars or {}

    # 外部 MCP server 工具：连接 + 适配成 ToolSpec，自动并入 ctx.run_with_tools 的 ReAct
    # 循环。运行结束统一 aclose 连接栈（防 stdio 子进程 / HTTP 连接泄漏）。
    mcp_tools, mcp_stack = await _load_mcp_tools(ctx.agent_def.key, manifest)

    # 连上 MCP 后所有路径都纳入 try/finally —— 即便 transport / AgentRun 构造抛异常，
    # 也保证 finally 关闭 MCP 连接栈（防 stdio 子进程 / HTTP 连接泄漏）。
    try:
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
            mcp_tools=mcp_tools,
        )
        # ctx.config = @agent(config=[Opt(default=)]) 的代码默认值 ← web 存值覆盖（双源：
        # 声明一次 default，运行时自动生效；作者不再写 ctx.config.get(k) or default 双写）。
        opt_defaults = {
            o.key: o.default for o in (manifest.config or []) if o.default is not None
        }
        run = AgentRun(
            transport=transport,
            agent_key=ctx.agent_def.key,
            query=_extract_query(ctx),
            messages=ctx.input if isinstance(ctx.input, list) else [],
            history=ctx.history,
            session_id=ctx.session_id,
            config={**opt_defaults, **(cfg.get("opts") or {})},
            attachments=ctx.attachments,
        )

        if manifest.is_class and not hasattr(target, "handle"):
            # 旧式兼容：classmethod astream(ctx)（裸 InvokeContext，不享 ctx/usage 上报）
            async for ev in target.astream(ctx):
                yield ev
            return

        # 函数式 / 新式类（handle(self, run) 注入 AgentRun）共用 _consume + 流末上报 usage
        result = target().handle(run) if manifest.is_class else target(run)
        async for ev in _consume(result, transport):
            yield ev
        # 流末上报累计 usage → InvokeResult.usage 非空 → A2A budget_consumed 真实
        u = transport.usage_total()
        if u.get("total_tokens"):
            yield StreamEvent(type=StreamEventType.metadata, data={"usage": u})
    finally:
        if mcp_stack is not None:
            from contextlib import suppress

            with suppress(Exception):
                await mcp_stack.aclose()


async def _load_mcp_tools(agent_key: str, manifest: Any) -> tuple[list[ToolSpec], Any]:
    """连声明的 MCP server，把其 tools 适配成 ToolSpec；返 (tools, 待关闭的连接栈)。

    加载失败仅 warning + 返空（不拖垮 agent）。连接栈由 run_agentkit 在 finally 关闭。
    """
    servers = getattr(manifest, "mcp_servers", None) or []
    if not servers:
        return [], None
    from dataclasses import asdict

    from chameleon.agentkit._mcp import load_mcp_tools

    try:
        descs, stack = await load_mcp_tools([asdict(s) for s in servers])
    except Exception as e:  # noqa: BLE001
        logger.warning("agentkit MCP 工具加载失败 agent={}: {}", agent_key, e)
        return [], None
    tools = [
        ToolSpec(
            name=d.name,
            description=d.description,
            parameters_schema=d.parameters_schema,
            handler=d.handler,
        )
        for d in descs
    ]
    return tools, stack


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
