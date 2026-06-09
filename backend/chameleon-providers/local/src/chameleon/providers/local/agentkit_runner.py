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

from chameleon.agentkit import AgentPaused, AgentRun, RuntimeTransport
from chameleon.agentkit._runtime import _PENDING_KEY, _content_to_text
from chameleon.agentkit._spec import (
    Doc,
    MediaResult,
    MemoryHit,
    ModelSlot,
    ToolSpec,
)
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

#: A2A 深度上限（含跨系统）——防 A2A 环无限递归（评审19 #3）。与进程内 engine a2a 的上限一致。
_A2A_MAX_DEPTH = 5


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


def _memory_text_projection(value: Any) -> str:
    """把记忆值投影成 embed 输入文本：str 原样；其它 JSON 序列化（中文不转义）。

    None / 空 → 空串（_index 据此删除向量行，保持与 KV 清空同步）。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


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
        call_agents: list[str] | None = None,
        sandboxed: bool = False,
    ) -> None:
        self._agent_key = agent_key
        #: 该 agent 是否声明沙箱（不可信）执行——禁其出站远程 A2A egress（评审19 #1）：沙箱
        #: --network none 被 broker（主进程有网）绕过，自声明 call_agents 白名单对不可信代码无效。
        self._sandboxed = sandboxed
        self._bindings = bindings or {}
        self._slots = slots or {}
        #: 该 agent 启用的平台工具 key（manifest.tools ∩ web tool_bindings）
        self._tool_keys = list(tool_keys or [])
        #: 外部 MCP server 工具（已适配成 ToolSpec），自动并入 run_tool_loop 本地工具
        self._mcp_tools = list(mcp_tools or [])
        #: ctx.call_agent allow-list（沙箱强制 target ∈ 此集；进程内不强制）
        self._call_agents = list(call_agents or [])
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
        from sqlalchemy.exc import IntegrityError

        from chameleon.data.infra.db import AsyncSessionLocal
        from chameleon.data.models import AgentMemory

        def _q():  # noqa: ANN202
            return select(AgentMemory).where(
                AgentMemory.agent_key == self._agent_key,
                AgentMemory.scope_ref == self._scope_ref,
                AgentMemory.mkey == key,
            )

        async with AsyncSessionLocal() as s:
            row = (await s.execute(_q())).scalar_one_or_none()
            if row is None:
                s.add(
                    AgentMemory(
                        agent_key=self._agent_key, scope_ref=self._scope_ref,
                        mkey=key, value={"v": value},
                    )
                )
            else:
                row.value = {"v": value}
            try:
                await s.commit()
            except IntegrityError:
                # 并发：另一事务已 insert 同 (agent_key,scope_ref,mkey)（uq 约束）——durable journal
                # 在同 run_id 并发/双击 resume 下会撞。回滚改 update，幂等 upsert（评审 #6）。
                await s.rollback()
                existing = (await s.execute(_q())).scalar_one_or_none()
                if existing is None:
                    # 非本键 uq 冲突（其它完整性错误）→ 重抛，不静默吞（评审16 🟠 收窄 except）。
                    raise
                existing.value = {"v": value}
                await s.commit()
        # 旁路语义索引（M1）：KV 是真相源、已落库；向量索引失败不回滚 set（warn 降级）。
        # 框架保留键（journal/checkpoint/pending）不入语义召回集，跳过 embed 省成本。
        if not (key.startswith("__chm_") and key.endswith("__")):
            await self._index_memory_vector(key, value)

    async def _index_memory_vector(self, key: str, value: Any) -> None:
        """旁路把记忆值的文本投影 embed 入 agent_memory_vector（经桥委托 engine）。"""
        from chameleon.providers.base.memory_vector_bridge import get_memory_index_fn

        index_fn = get_memory_index_fn()
        if index_fn is None:
            return  # 桥未接（无向量后端）→ memory 退化为纯 KV
        try:
            await index_fn(
                self._agent_key, self._scope_ref, key, _memory_text_projection(value)
            )
        except Exception:  # noqa: BLE001 —— 索引尽力而为，绝不拖垮 set
            logger.warning("memory 向量索引失败 agent={} key={}", self._agent_key, key)

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

    async def memory_search(
        self, query: str, *, top_k: int = 5, min_score: float = 0.0
    ) -> list[MemoryHit]:
        if not self._scope_ref:
            return []
        from chameleon.providers.base.memory_vector_bridge import get_memory_search_fn

        search_fn = get_memory_search_fn()
        if search_fn is None:
            return []  # 桥未接（无向量后端）→ 无语义召回
        rows = await search_fn(
            self._agent_key, self._scope_ref, query, top_k=top_k, min_score=min_score
        )
        if not rows:
            return []
        # 回填原始值（KV 真相源）：一次批量查命中 key 的 value，避免 N 次往返。
        keys = [r["key"] for r in rows if r.get("key")]
        values = await self._memory_values_for(keys)
        return [
            MemoryHit(
                key=r["key"],
                value=values.get(r["key"]),
                text=r.get("text", ""),
                score=float(r.get("score", 0.0)),
            )
            for r in rows
            if r.get("key")
        ]

    async def _memory_values_for(self, keys: list[str]) -> dict[str, Any]:
        """批量取一组 mkey 的原始值（按本 agent + scope 隔离）。"""
        if not keys:
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
                        AgentMemory.mkey.in_(keys),
                    )
                )
            ).scalars().all()
        return {
            r.mkey: (r.value.get("v") if isinstance(r.value, dict) else None)
            for r in rows
        }

    async def call_agent(self, target: str, *, input: str) -> str:
        from chameleon.providers.base.a2a_bridge import get_a2a_caller

        # 开放 A2A 出站（Slice A.2）：target 是 http(s) URL → 调远程 A2A agent；进程内 key 走下方
        # a2a_bridge。URL 须在 call_agents 声明白名单内（统一 scope：声明你调的远程端点，防任意
        # egress/SSRF——尤其沙箱不可信代码经 broker 发远程调用）。
        if target.startswith(("http://", "https://")):
            return await self._call_remote_a2a(target, input)

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

    async def _remote_a2a_call(self, url: str, input: str) -> tuple[str, int]:
        """远程 A2A 调用 + 全部红线，返 (answer, est_tokens)，**不计费**——计费时机由调用方定
        （call_agent 立即扣，gather 统一扣，避免双扣）。红线：① 沙箱(不可信)agent 禁远程 egress
        （评审19 #1：broker 在主进程有网会绕过 child --network none）；② URL 须声明在 call_agents
        （防任意 egress）；③ 跨系统深度上限防 A2A 环无限递归（评审19 #3）；④ 远程 token 不可信→
        按答案长度本地粗估；⑤ 远程输出 untrusted。"""
        if self._sandboxed:
            raise RuntimeError(
                "沙箱(不可信)agent 禁止出站远程 A2A——broker 在主进程有网会绕过 --network none "
                "隔离。需远程协作的 agent 不应声明 sandboxed=True。"
            )
        if url not in self._call_agents:
            raise RuntimeError(
                f"远程 A2A 目标未声明：{url} 不在 @agent(call_agents=[...]) 白名单内"
                f"（声明你调用的远程端点，防任意网络出站）"
            )
        if self._a2a_depth + 1 > _A2A_MAX_DEPTH:
            raise RuntimeError(
                f"A2A 深度超限（>{_A2A_MAX_DEPTH}）：防跨系统 A2A 环无限递归（评审19 #3）"
            )
        from chameleon.integrations.a2a import A2AClient

        tc = current_trace_context()
        trace_id = self._request_id or (tc.request_id if tc else None) or self._session_id
        self.emit(
            StreamEvent(
                type=StreamEventType.step,
                data={"name": f"调用远程 A2A {url}", "status": "success",
                      "output": {"target": url, "remote": True}},
            )
        )
        # depth+1 经 metadata 透传——远程若是本系统的 /a2a 入站，会读它续计深度（不重置成 0）
        answer = await A2AClient(url).call(
            input, trace_id=trace_id, depth=self._a2a_depth + 1
        )
        # 远程 token 不可信，按答案长度本地粗估（≈chars/4，截上限防超长撑爆）
        return answer, min(max(1, len(answer) // 4), 100_000)

    async def _call_remote_a2a(self, url: str, input: str) -> str:
        """ctx.call_agent 的远程分支：调用 + 立即扣预算/计 usage（成本闸对远程也生效）。"""
        answer, est = await self._remote_a2a_call(url, input)
        self._charge(est)
        self.track_usage({"total_tokens": est})
        return answer

    async def gather(
        self, calls: list[tuple[str, str]], *, timeout: float | None = None
    ) -> list[str]:
        """并行扇出子智能体（预算均分防超支版）。timeout 秒每分支超时上限（评审8 🟠）。

        N 个并行分支若各读同一 self._budget 会各拿全额→可能超支；故按分支数均分预算
        （每支 budget//N），事后按实际总消耗统一扣减 + 计入 usage。trace_id/depth/scope
        与 call_agent 一致。保序返回（asyncio.gather 保序）。
        """
        import asyncio

        from chameleon.providers.base.a2a_bridge import get_a2a_caller

        n = len(calls)
        if n == 0:
            return []
        caller = get_a2a_caller()
        # 仅当存在进程内目标时才需 in-process caller；纯远程 A2A（全 URL）扇出不依赖它
        has_inprocess = any(not t.startswith(("http://", "https://")) for t, _ in calls)
        if caller is None and has_inprocess:
            raise RuntimeError("A2A caller 未注入（app 启动应调 wire_a2a_bridge）")
        tc = current_trace_context()
        trace_id = self._request_id or (tc.request_id if tc else None) or self._session_id
        if not trace_id:
            raise RuntimeError("ctx.gather 需要 trace_id / session_id 至少其一")
        share = max(1, self._budget // n)  # 预算均分：防并行分支各拿全额超支
        self.emit(
            StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": f"并行调用 {n} 个子智能体",
                    "status": "success",
                    "output": {"targets": [t for t, _ in calls]},
                },
            )
        )

        async def _one(target: str, inp: str) -> dict[str, Any]:
            # 远程 A2A 分支：target 是 URL → 走 A2AClient（与 call_agent 一致，含全部红线），
            # 返 dict 供 gather 统一计费（不在此扣，避免与下方 total 双扣）。
            if target.startswith(("http://", "https://")):
                rcoro = self._remote_a2a_call(target, inp)
                answer, est = await (asyncio.wait_for(rcoro, timeout) if timeout else rcoro)
                return {"answer": answer, "tokens": est}
            coro = caller(
                source=self._agent_key,
                target=target,
                input=inp,
                trace_id=trace_id,
                budget_remaining=share,
                depth=self._a2a_depth + 1,
            )
            return await (asyncio.wait_for(coro, timeout) if timeout else coro)

        # return_exceptions=True：即使某分支失败，也要先结清已成功分支的预算/usage——
        # 否则一支抛异常会让 _charge/track_usage 整体跳过，成功兄弟已花的钱被"洗白"
        # （成本闸在部分失败场景泄漏，评审7 🔴）。结清后再重抛首个异常保留 fail-fast 语义。
        outs = await asyncio.gather(*(_one(t, i) for t, i in calls), return_exceptions=True)
        ok = [o for o in outs if not isinstance(o, BaseException)]
        total = sum(int(o.get("tokens") or 0) for o in ok)
        self._charge(total)
        self.track_usage({"total_tokens": total})
        errs = [o for o in outs if isinstance(o, BaseException)]
        if errs:
            raise errs[0]
        return [o.get("answer") or "" for o in outs]

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


def _should_sandbox(manifest: Any) -> bool:
    """`@agent(sandboxed=True)` 是否走真隔离子进程执行（T4-2 Phase 2）。

    - 非沙箱声明 → False。
    - CHAMELEON_SANDBOX_FORCE=1 → True（dev 也强制走沙箱，便于本地验证隔离）。
    - 非生产 → False（开发态进程内跑，便利；dev 默认不隔离）。
    - 生产 + sandboxed → True 走真沙箱（SubprocessSandboxRuntime）；除非显式
      CHAMELEON_SANDBOX_ALLOW_INPROCESS=1 表示「源码可信，进程内跑」才 False。
    """
    if not getattr(manifest, "sandboxed", False):
        return False
    import os

    if os.environ.get("CHAMELEON_SANDBOX_FORCE", "").strip().lower() in ("1", "true", "yes"):
        return True
    from chameleon.core.sandbox import is_production

    if not is_production():
        return False
    allow = os.environ.get("CHAMELEON_SANDBOX_ALLOW_INPROCESS", "").strip().lower()
    return allow not in ("1", "true", "yes")


def _assert_isolation_for_tier(manifest: Any, key: str) -> None:
    """untrusted 信任级的 fail-closed 闸：生产必须 docker 真隔离，否则拒绝运行。

    子进程档只擦 env 凭据，不隔离 FS/网络——对"陌生人代码"不够。untrusted agent 若部署未配
    CHAMELEON_SANDBOX_RUNTIME=docker，宁可拒绝运行也不静默退化到漏隔离子进程（防 RCE）。
    """
    import os

    if getattr(manifest, "trust_tier", "internal") != "untrusted":
        return
    from chameleon.core.sandbox import is_production

    if not is_production():
        return
    runtime = os.environ.get("CHAMELEON_SANDBOX_RUNTIME", "subprocess").strip().lower()
    if runtime != "docker":
        raise RuntimeError(
            f"untrusted agent {key} 要求 docker 真隔离，但 CHAMELEON_SANDBOX_RUNTIME≠docker；"
            f"拒绝在 FS/网络未隔离的子进程档运行不可信代码（fail-closed）。请配置 docker runtime。"
        )


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

    # durable fail-closed（评审 #2）：journal/HITL 落 AgentMemory 按 scope_ref 持久化；无身份
    # （scope_ref 空）则 memory no-op → journal 永久失效、ask_human resume 后无限重暂停。绝不
    # 静默退化：durable 需持久化 scope，缺则直接拒（而非跑成坏 journal）。须在 _load_mcp_tools
    # **之前** raise——否则 mcp_stack 已开却未进 try/finally，会泄漏 stdio/HTTP 连接（评审16）。
    scope_ref = cvars.get("end_user_id") or ctx.session_id
    if manifest.durable and not scope_ref:
        raise RuntimeError(
            f"durable agent '{ctx.agent_def.key}' 需持久化 scope（end_user_id 或 session_id）"
            f"才能 journal 重放 / HITL resume；当前无身份。请在带会话/end_user 的上下文调用。"
        )

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
            scope_ref=scope_ref,
            mcp_tools=mcp_tools,
            call_agents=list(manifest.call_agents or []),
            sandboxed=manifest.sandboxed,  # 沙箱 agent 禁出站远程 A2A（评审19 #1）
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
            # durable：开 journal memoization + ctx.ask_human HITL；run_id 用 request_id 做 per-run
            # 隔离。resume 时须以同 request_id 重新 invoke（重放至 ask 点续跑）。
            durable=manifest.durable,
            run_id=ctx.request_id,
        )

        # durable resume：resume 端点以同 request_id 重新 invoke 并经 context_vars 带回人工答案，
        # 跑 handle 前回填进 journal 的 ask 点，使重放在该 call_index 取答案续跑过暂停点。
        # _seed_resume 校验失败（run 未暂停 / run_id 错 / call_index 错位）→ emit 清晰 error 事件
        # 而非让裸异常被上层吞成不透明报错（评审17）。
        if manifest.durable and "_resume_answer" in cvars:
            try:
                await run._seed_resume(int(cvars["_resume_call_index"]), cvars["_resume_answer"])
            except RuntimeError as e:
                yield StreamEvent(type=StreamEventType.error, data={"message": str(e)})
                return

        # 记忆自动注入（M2 working / M3 observational）：声明对应能力且有 scope（身份）时，run 前
        # 载入槽 + 渲染成 system 块挂到 run，_build_messages 每轮并入。无 scope 跳过（需持久化 scope）。
        if scope_ref:
            from chameleon.agentkit._runtime import _inject_memory_context

            await _inject_memory_context(transport, manifest, run)

        # 沙箱路由：@agent(sandboxed=True) 在生产/force 下走隔离子进程执行（handle 在子
        # 进程，ctx 资源经 broker=transport 受控解析；凭据/DB 只在主进程）。
        if _should_sandbox(manifest):
            from chameleon.providers.local.sandbox import run_sandboxed

            # fail-closed：untrusted（陌生人代码）生产必须 docker 真隔离；无 docker runtime
            # 时拒绝运行，绝不静默退化到 FS/网络未隔离的子进程（路线图 §6 信任级闸）。
            _assert_isolation_for_tier(manifest, ctx.agent_def.key)
            logger.info("agentkit agent {} 走沙箱隔离执行", ctx.agent_def.key)
            async for ev in run_sandboxed(
                module=cfg["__agentkit_module__"],
                attr=cfg["__agentkit_attr__"],
                query=_extract_query(ctx),
                broker=transport,
                session_id=ctx.session_id,
                config={**opt_defaults, **(cfg.get("opts") or {})},
            ):
                yield ev
            return

        if manifest.is_class and not hasattr(target, "handle"):
            # 旧式兼容：classmethod astream(ctx)（裸 InvokeContext，不享 ctx/usage 上报）
            async for ev in target.astream(ctx):
                yield ev
            return

        # 函数式 / 新式类（handle(self, run) 注入 AgentRun）共用 _consume + 流末上报 usage
        result = target().handle(run) if manifest.is_class else target(run)
        try:
            async for ev in _consume(result, transport):
                yield ev
        except AgentPaused as paused:
            # durable HITL：ctx.ask_human 无答案 → run 暂停等人工输入。不算失败：发 step 暂停信号
            # （pending 已落 AgentMemory），本次流优雅结束。resume 端点回填答案后以同 request_id
            # 重新 invoke，journal 重放至 ask 点取答案续跑。
            logger.info("agentkit agent {} 暂停等人工输入 @call_index={}",
                        ctx.agent_def.key, paused.call_index)
            # 评审 #5：先 drain pause 前已 emit 但未产出的缓冲事件（citation/tool_result/step），
            # 再上报 pre-pause 累计 usage——否则暂停时这些 trace 事件丢失、pre-pause token 漏计。
            for ev in transport.drain():
                yield ev
            u = transport.usage_total()
            if u.get("total_tokens"):
                yield StreamEvent(type=StreamEventType.metadata, data={"usage": u})
            yield StreamEvent(
                type=StreamEventType.step,
                data={"name": "human_input_pending", "status": "paused",
                      "prompt": paused.prompt, "call_index": paused.call_index,
                      "run_id": paused.run_id},
            )
            return
        # durable resume 跑完（未再暂停）→ 清 pending：否则该 pending 永久残留，运营「待人工处理」
        # 列表会把已解决的 run 当待办（评审22 C2）。不在 resume 起点清是为保幂等重试；再暂停则
        # ask_human 会重写新 pending。非 resume 的 fresh run 无 pending，跳过避免无谓写。
        if manifest.durable and "_resume_answer" in cvars:
            await transport.memory_set(_PENDING_KEY, None)
        # 流末上报累计 usage → InvokeResult.usage 非空 → A2A budget_consumed 真实
        u = transport.usage_total()
        if u.get("total_tokens"):
            yield StreamEvent(type=StreamEventType.metadata, data={"usage": u})
        # observational memory（M3）：长对话 run 成功结束后异步触发 Observer→Reflector 压缩，
        # 把旧对话压成稠密观察落 __chm_observations__（下轮自动注入）。fire-and-forget 不阻塞本次流。
        if manifest.observe_memory and scope_ref:
            _maybe_trigger_compression(ctx.agent_def.key, scope_ref, ctx.history)
    finally:
        if mcp_stack is not None:
            from contextlib import suppress

            with suppress(Exception):
                await mcp_stack.aclose()


#: observational memory 后台压缩任务的强引用集（防 asyncio "task was destroyed but pending"）。
_COMPRESS_BG_TASKS: set[Any] = set()


def _compress_threshold_chars() -> int:
    """触发 observational 压缩的对话字符阈值（settings 可调，默认 4000）。"""
    from chameleon.core.config.json_settings import chameleon_settings

    return int(chameleon_settings.get("agentkit.memory.compress_threshold_chars") or 4000)


def _extract_conversation_text(history: list[Any]) -> str:
    """把 history 拼成 "role: text" 多行文本（observational 压缩的输入）。"""
    parts: list[str] = []
    for m in history or []:
        role = getattr(m, "role", "user")
        text = m.text() if hasattr(m, "text") else str(m)
        if text:
            parts.append(f"{role}: {text}")
    return "\n".join(parts)


def _maybe_trigger_compression(
    agent_key: str, scope_ref: str, history: list[Any]
) -> None:
    """长对话才异步触发压缩（短对话无压缩价值，省后台 LLM 成本）。fire-and-forget。"""
    conversation = _extract_conversation_text(history)
    if len(conversation) < _compress_threshold_chars():
        return
    import asyncio

    task = asyncio.create_task(
        _compress_memory_bg(agent_key, scope_ref, conversation)
    )
    _COMPRESS_BG_TASKS.add(task)
    task.add_done_callback(_COMPRESS_BG_TASKS.discard)


async def _compress_memory_bg(
    agent_key: str, scope_ref: str, conversation: str
) -> None:
    """后台跑 Observer→Reflector 压缩并落 __chm_observations__（非破坏：合并不删原始）。

    best-effort：任何失败只 warning（绝不影响已结束的主调用）。复用 aikit 任务（AI 内核），
    落库走 InProcessTransport.memory_set（保留键 → 不进语义索引，靠注入交付）。
    """
    from chameleon.agentkit._runtime import _OBSERVATIONS_KEY
    from chameleon.aikit.tasks.memory import compress_observations

    try:
        t = InProcessTransport(
            agent_key=agent_key, bindings={}, slots={}, scope_ref=scope_ref
        )
        existing = await t.memory_get(_OBSERVATIONS_KEY, "")
        existing = existing if isinstance(existing, str) else ""
        updated = await compress_observations(existing, conversation)
        if updated and updated != existing:
            await t.memory_set(_OBSERVATIONS_KEY, updated)
            logger.info(
                "observational memory 压缩完成 agent={} scope={}", agent_key, scope_ref
            )
    except Exception:  # noqa: BLE001 —— 后台 best-effort，不向上抛
        logger.warning("observational memory 压缩失败 agent={}", agent_key)


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
