"""运行时契约 —— AgentRun（作者面）与 RuntimeTransport（可插拔后端）。

Phase 0：仅定义公共签名 + 抽象，**不接实现**。
- `RuntimeTransport`：ctx 背后的资源解析 + 观测后端，两种实现（后续 phase）：
    · InProcessTransport：站内进程内，直连 routing / kb / observe
    · HttpDevTransport：本地自测，HTTP 回调 dev 服务 /v1/dev/{llm,kb,trace}
- `AgentRun`：注入给作者 `handle(ctx)` 的上下文；模型 / KB / trace 隐式从这里拿。

模型 / KB 解析全部落到平台「已配置资源池」，code/kb_key 校验，非任填。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

from chameleon.agentkit._spec import Doc, MediaResult, ToolSpec

if TYPE_CHECKING:
    from chameleon.core.runtime_types import Message, StreamEvent


class KbHandle(Protocol):
    """`ctx.kb` —— 知识库检索门面。"""

    async def search(
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
        """kbs 给定=代码点名这些已配置 KB；否则用该 agent web 关联的 KB。

        高级检索（接平台 hybrid 管道）：mode=vector/keyword/hybrid（默认跟随 KB 配置→
        hybrid）；rerank=是否重排（None 跟随 KB 配置）；expand=multi-query 变体数；
        hyde=是否用假设答案 embed。平台未接桥时回退基础向量检索。
        """
        ...


class MediaHandle(Protocol):
    """`ctx.media` —— 多模态生成门面（图/视频，复用平台生成模型 + 对象存储）。"""

    async def generate(
        self,
        *,
        kind: str,
        prompt: str,
        slot: str | None = None,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        input_images: list[str] | None = None,
    ) -> MediaResult:
        """生成一张图 / 一段视频。

        kind=image/video；slot 走该 agent 模型槽绑定链（声明 ModelSlot(kind="image")），
        model 直接点名已配置生成模型 code；params 覆盖默认（尺寸/比例/步数/时长…）；
        input_images 给图生视频的首帧。进度自动 emit step、产物自动 emit + usage。
        """
        ...


class MemoryHandle(Protocol):
    """`ctx.memory` —— 跨会话 kv 记忆门面。

    作用域：优先 end_user_id（跨会话），无身份退化 session_id。值须 JSON 可序列化。
    """

    async def get(self, key: str, default: Any = None) -> Any: ...

    async def set(self, key: str, value: Any) -> None: ...

    async def all(self) -> dict[str, Any]: ...


class RuntimeTransport(ABC):
    """ctx 背后的可插拔后端：解析已配置资源 + 观测。"""

    @abstractmethod
    def chat_model(self, *, slot: str | None = None, model: str | None = None) -> Any:
        """解析并返回配置好的 LangChain chat model。

        - slot：走该 agent 的绑定链（web 绑定 → 槽 default → 系统默认）。
        - model：直接点名某「已配置且启用」模型 code（= `llm_by_name`），校验非法即报错。
        - 两者互斥；都不给 = 系统默认（= `llm()`）。
        """
        ...

    @abstractmethod
    def structured_model(
        self, *, slot: str | None = None, model: str | None = None, schema: type
    ) -> Any:
        """返回一个绑定了结构化输出（`with_structured_output(schema)`）的模型；
        其 `ainvoke` 直接返回校验后的 pydantic 实例。"""
        ...

    @abstractmethod
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
        """检索；自动记 citation。kbs 校验须命中已配置 KB。

        mode/rerank/expand/hyde 走平台高级检索管道（接桥）；未接桥回退基础向量。
        """
        ...

    @abstractmethod
    def run_tool_loop(
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
        """跑 ReAct / function-calling 循环，yield 最终答案文本增量。

        绑平台工具（platform_keys ∪ 该 agent 绑定集）+ 本地工具（local_tools），
        多轮：模型出 tool_calls → 执行（平台走 registry / 本地走 handler）→ 回填 →
        续轮；无 tool_calls 即出最终文本。自动 emit tool_call/tool_result 事件、
        开 span、累加 usage。`max_steps` 为循环轮次上限；`max_tokens` 为本轮循环 token
        上限（与 agent 总预算共同构成成本闸，任一耗尽即截断收口）。
        """
        ...

    @abstractmethod
    async def memory_get(self, key: str, default: Any = None) -> Any:
        """读 kv 记忆（按本 agent + 作用域）。"""
        ...

    @abstractmethod
    async def memory_set(self, key: str, value: Any) -> None:
        """写 kv 记忆（upsert）。"""
        ...

    @abstractmethod
    async def memory_all(self) -> dict[str, Any]:
        """取本 agent + 作用域下全部 kv。"""
        ...

    @abstractmethod
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
        """生成图/视频（复用平台生成模型 + 对象存储）；自动 emit 进度/产物 + usage。"""
        ...

    @abstractmethod
    async def call_agent(self, target: str, *, input: str) -> str:
        """调另一个已注册智能体（A2A）；返回其答案文本。

        trace 不断链 / 预算 / 深度等红线由实现层（经 engine a2a）统一满足。
        """
        ...

    async def gather(
        self, calls: list[tuple[str, str]], *, timeout: float | None = None
    ) -> list[str]:
        """并行扇出调用多个子智能体（map-reduce），返回与入参同序的答案列表。

        默认实现：并发跑各 call_agent（dev/fake/sandbox 直接可用）。生产 InProcess 档覆盖
        为「预算按分支数均分」防并行分支各拿全额超支（成本闸在并发下仍收口）。
        timeout（秒）：每分支超时上限，防某支 hang 永等（评审8 🟠）；None=不限。
        """
        import asyncio

        async def _one(t: str, i: str) -> str:
            coro = self.call_agent(t, input=i)
            return await (asyncio.wait_for(coro, timeout) if timeout else coro)

        return list(await asyncio.gather(*(_one(t, i) for t, i in calls)))

    @abstractmethod
    def span(self, name: str, *, type: str = "span") -> Any:
        """打开一个 observe span（async context manager）。"""
        ...

    @abstractmethod
    def emit(self, event: StreamEvent) -> None:
        """透传一个自定义 StreamEvent 到输出流。"""
        ...

    @abstractmethod
    def track_usage(self, usage: dict[str, int] | None) -> None:
        """累计本次运行的 token 用量（complete/stream/工具循环/子调用共账）。

        run_agentkit 流末把累计值 emit 成 usage 事件 → InvokeResult.usage 非空 →
        A2A budget_consumed 真实 → 扇出预算闸生效（否则成本闸对 agentkit 子 agent no-op）。
        """
        ...


#: ctx.checkpoint/restore 在 memory 里的保留键（前缀防与作者自定义 key 冲突）。
_CHECKPOINT_KEY = "__chm_checkpoint__"


class _RouteChoice(BaseModel):
    """ctx.route 的 LLM 路由决策结构化输出。"""

    agent_key: str
    reason: str = ""


class AgentRun:
    """注入给作者 `handle(ctx)` / `astream` 的运行时上下文。

    绑定「本 agent 的页面配置 + 本次请求」；模型 / KB / trace 都从这里隐式拿，
    作者不 import `llm()` / `search_kb()`、不传 agent_key、不手写 trace。
    """

    def __init__(
        self,
        *,
        transport: RuntimeTransport,
        agent_key: str,
        query: str,
        messages: list[Message],
        history: list[Message],
        session_id: str | None,
        config: dict[str, Any],
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        self._t = transport
        self.agent_key = agent_key
        self.query = query
        self.messages = messages
        self.history = history
        self.session_id = session_id
        self.config = config
        #: 本次调用附带的附件原始 dict（{object_url, filename, mime, size}）。
        #: 图/音已由 service 翻进 messages 多模态 ContentBlock，作者主要拿这里
        #: 的元信息做条件分支；文档/数据类异步入临时 KB，通过 ctx.kb.search()
        #: 也能拿到检索结果。
        self.attachments: list[dict[str, Any]] = attachments or []

    # —— 模型（slot=走绑定链；model=点名已配置 code，二选一）——

    def llm(self, slot: str = "chat", *, model: str | None = None) -> Any:
        """低层：返回配置好的 LangChain chat model，可任意 LCEL 组合。"""
        return self._t.chat_model(slot=None if model else slot, model=model)

    def wrap(self, model: Any) -> Any:
        """逃生口（档 C，少用）：直接用作者自带的 LangChain chat model。

        平台模型库确实没有该模型时的定制出口——绕过平台路由 / 凭证 / 计费（这些都不
        经过平台）。返回对象与 `ctx.llm()` 同形（可 ainvoke/astream），可直接用或喂给
        LCEL。默认走 `ctx.llm(slot/model=)`（已配置资源池 + 自动 trace/计费），仅极端
        定制才用 wrap。
        """
        return model

    async def complete(
        self,
        *,
        slot: str = "chat",
        model: str | None = None,
        system: str | None = None,
        user: str,
        context: Any = None,
        schema: type | None = None,
        **kw: Any,
    ) -> Any:
        """高层糖：一次性出文本，自动 generation span + usage。

        给了 `schema`（一个 pydantic BaseModel 子类）则走结构化输出：返回校验后的
        模型**实例**（而非 str）。底层用 langchain `with_structured_output`。
        """
        msgs = self._build_messages(system, user, context)
        if schema is not None:
            structured = self._t.structured_model(
                slot=None if model else slot, model=model, schema=schema
            )
            async with self._t.span("llm.complete", type="span"):
                resp = await structured.ainvoke(msgs, **kw)
            self._t.track_usage(_usage_of(resp))
            return resp
        chat = self._t.chat_model(slot=None if model else slot, model=model)
        async with self._t.span("llm.complete", type="span"):
            resp = await chat.ainvoke(msgs, **kw)
        self._t.track_usage(_usage_of(resp))
        return _content_to_text(resp)

    async def stream(
        self,
        *,
        slot: str = "chat",
        model: str | None = None,
        system: str | None = None,
        user: str,
        context: Any = None,
        **kw: Any,
    ) -> AsyncIterator[str]:
        """高层糖：流式出文本（逐增量 yield），自动 span + usage。"""
        chat = self._t.chat_model(slot=None if model else slot, model=model)
        msgs = self._build_messages(system, user, context)
        async with self._t.span("llm.stream", type="span"):
            async for chunk in chat.astream(msgs, **kw):
                self._t.track_usage(_usage_of(chunk))  # usage 通常在末 chunk
                text = _content_to_text(chunk)
                if text:
                    yield text

    # —— 工具调用（ReAct 循环糖）——

    async def run_with_tools(
        self,
        *,
        user: str | None = None,
        system: str | None = None,
        slot: str = "chat",
        model: str | None = None,
        tools: list[Any] | None = None,
        tool_keys: list[str] | None = None,
        context: Any = None,
        max_steps: int = 6,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """高层糖：自动 ReAct 工具循环，逐增量 yield 最终答案文本。

        - `tools`：本地 `@tool` 声明的函数（或 ToolSpec）；随代码走。
        - `tool_keys`：本轮临时追加点名的平台工具；与 `@agent(tools=)` / web 绑定
          的平台工具合并。
        - 工具调用 / 结果自动 emit 成 tool_call / tool_result 事件（作者无需手动
          yield），自动 trace + usage 累加。`max_steps` 防无限循环；`max_tokens`
          为本轮循环 token 上限（与 agent 总预算共同构成成本闸）。
        """
        user_text = user if user is not None else self.query
        local: list[ToolSpec] = []
        for t in tools or []:
            spec = getattr(t, "__tool_spec__", None)
            if spec is None and isinstance(t, ToolSpec):
                spec = t
            if spec is not None:
                local.append(spec)
        msgs = self._build_messages(system, user_text, context)
        async for delta in self._t.run_tool_loop(
            messages=msgs,
            slot=None if model else slot,
            model=model,
            platform_keys=list(tool_keys or []),
            local_tools=local,
            max_steps=max_steps,
            max_tokens=max_tokens,
        ):
            yield delta

    def _build_messages(
        self, system: str | None, user: str, context: Any
    ) -> list[tuple[str, str]]:
        """组装 (role, content) 列表 —— system + history + 本轮 user（含可选 context）。

        不依赖 langchain：LangChain chat model 的 ainvoke/astream 接受 (role, content) 元组。
        """
        msgs: list[tuple[str, str]] = []
        if system:
            msgs.append(("system", system))
        for m in self.history:
            role = getattr(m, "role", "user")
            if role not in ("system", "user", "assistant"):
                continue
            msgs.append((role, m.text()))
        user_text = user
        if context:
            ctx_text = context if isinstance(context, str) else _docs_to_text(context)
            user_text = f"参考资料：\n{ctx_text}\n\n问题：{user}"
        msgs.append(("user", user_text))
        return msgs

    # —— 子智能体（A2A）——

    async def call_agent(self, target: str, *, input: str) -> str:
        """调另一个已注册智能体，返回其答案文本。

        source / trace_id / depth+1 / 预算自动从本次运行上下文透传；嵌套深度、
        token 预算、trace 串联等红线由底层 engine a2a 统一守。
        """
        return await self._t.call_agent(target, input=input)

    async def gather(
        self, calls: list[tuple[str, str]], *, timeout: float | None = None
    ) -> list[str]:
        """并行扇出调用多个子智能体（map-reduce），返回与入参同序的答案列表。

        每项为 `(target_agent_key, input)`。比手写 `asyncio.gather(ctx.call_agent(...))`
        多了预算协调——生产档把剩余预算按分支数均分给各并行分支，防并行各拿全额超支。
        嵌套深度 / trace 串联 / scope 等红线与 call_agent 一致。

        例：`a, b = await ctx.gather([("agent-a", q1), ("agent-b", q2)])`
        `timeout`（秒）：每分支超时上限，防某子智能体 hang 拖垮整个扇出；None=不限。
        """
        return await self._t.gather(calls, timeout=timeout)

    async def handoff(self, target: str, *, instruction: str | None = None) -> str:
        """把当前对话**移交**给目标子智能体接手作答（控制权转移）。

        与 call_agent 的区别：handoff 把本轮**完整对话上下文**（history + 当前 query）打包
        进 input 传给目标，目标据全局上下文接续——适合"分诊后转专家"等场景。call_agent 只
        传一条 input。A2A 路径有意不透传 history，故由此处按约定打包（见 engine a2a 设计）。
        `instruction` 可选，给目标的额外接手指示。

        注：这是"带上下文一次性委托"，非 OpenAI 式可来回的双向 handoff（目标答完即返）。
        """
        parts: list[str] = []
        for m in self.history:
            role = getattr(m, "role", "user")
            parts.append(f"{role}: {m.text()}")
        parts.append(f"user: {self.query}")
        convo = "\n".join(parts)
        head = instruction.strip() if instruction else "请接手以下对话并作答。"
        return await self.call_agent(target, input=f"{head}\n\n对话上下文：\n{convo}")

    async def route(
        self,
        query: str,
        agents: list[tuple[str, str]],
        *,
        slot: str = "chat",
        model: str | None = None,
    ) -> str:
        """supervisor 路由：LLM 据各候选子智能体的能力描述选最合适的，委托并返回其答案。

        `agents`：`[(agent_key, capability_description), ...]`。常见多智能体编排模式——
        总控按问题把任务分派给专长 agent。纯建在 ctx.complete（结构化选择）+ ctx.call_agent
        上，路由决策自动进 trace。单候选直接委托，零候选报错。

        例：`ans = await ctx.route(ctx.query, [("sql-bot","查数据库"),("doc-bot","查文档")])`
        """
        if not agents:
            raise ValueError("ctx.route 至少需要一个候选 agent")
        keys = [k for k, _ in agents]
        if len(agents) == 1:
            return await self.call_agent(keys[0], input=query)
        options = "\n".join(f"- {k}: {d}" for k, d in agents)
        # 结构化路由：模型不支持 function_calling / 调用失败时不让 route 整体炸——回退首个
        # 候选并把失败诊断标进 trace（评审8 🟠）。LLM 选了候选集外的 key 同样回退（评审7 🟡）。
        try:
            choice = await self.complete(
                slot=slot,
                model=model,
                schema=_RouteChoice,
                system="你是任务路由器。根据用户问题，从候选智能体里选最合适处理的那一个，"
                "返回它的 agent_key（必须是候选之一）。",
                user=f"候选智能体：\n{options}\n\n用户问题：{query}",
            )
            fallback = choice.agent_key not in keys
            chosen = keys[0] if fallback else choice.agent_key
            reason = getattr(choice, "reason", "")
        except Exception as e:  # noqa: BLE001
            chosen, fallback = keys[0], True
            reason = f"结构化路由失败({type(e).__name__})，回退首个候选"
        from chameleon.core.runtime_types import StreamEvent, StreamEventType

        self.emit(
            StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": f"路由到 {chosen}",
                    "status": "success",
                    "output": {"chosen": chosen, "fallback": fallback, "reason": reason},
                },
            )
        )
        return await self.call_agent(chosen, input=query)

    # —— 知识库 ——

    @property
    def kb(self) -> KbHandle:
        return _KbProxy(self._t)

    # —— 记忆（跨会话 kv）——

    @property
    def memory(self) -> MemoryHandle:
        return _MemoryProxy(self._t)

    # —— 多模态生成（图/视频）——

    @property
    def media(self) -> MediaHandle:
        return _MediaProxy(self._t)

    # —— 追踪（直接转发 transport，Phase 0 即可用其抽象契约）——

    def span(self, name: str, *, type: str = "span") -> Any:
        """打开一段 observe span（async context manager）。"""
        return self._t.span(name, type=type)

    def emit(self, event: StreamEvent) -> None:
        """透传一个自定义 StreamEvent。"""
        self._t.emit(event)

    # —— durable：检查点 / 恢复（崩溃恢复 author 进度）——

    async def checkpoint(self, state: dict[str, Any]) -> None:
        """存一份 durable 执行状态快照——长任务/多步 agent 崩溃或中断后，下次同 end_user/会话
        调用 `ctx.restore()` 取回，从断点续跑而非从头。

        底层复用 ctx.memory 的持久化（按 end_user 隔离），故 `state` 须 JSON 可序列化。
        这是 durable execution 的崩溃恢复底座；HITL 暂停/重放（ctx.ask_human）见路线图后续分片。
        """
        import json

        # 平台落 JSON 列：不可序列化的 state（datetime/自定义类）在 commit 时才裸炸；这里前置
        # 校验给友好报错，且让 standalone（存活引用、不序列化）与平台行为一致（评审10 🟠）。
        try:
            json.dumps(state)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"ctx.checkpoint(state) 的 state 须 JSON 可序列化（落库持久化）；当前不可序列化：{e}"
            ) from e
        await self._t.memory_set(_CHECKPOINT_KEY, state)

    async def restore(self, default: Any = None) -> Any:
        """取回上次 `ctx.checkpoint()` 存的状态快照；无则返 `default`。"""
        return await self._t.memory_get(_CHECKPOINT_KEY, default)


class _MediaProxy:
    """`ctx.media` 的实现：转发给 transport（结构上满足 MediaHandle）。"""

    def __init__(self, transport: RuntimeTransport) -> None:
        self._t = transport

    async def generate(
        self,
        *,
        kind: str,
        prompt: str,
        slot: str | None = None,
        model: str | None = None,
        params: dict[str, Any] | None = None,
        input_images: list[str] | None = None,
    ) -> MediaResult:
        return await self._t.media_generate(
            kind=kind,
            prompt=prompt,
            slot=slot,
            model=model,
            params=params,
            input_images=input_images,
        )


class _MemoryProxy:
    """`ctx.memory` 的实现：转发给 transport（结构上满足 MemoryHandle）。"""

    def __init__(self, transport: RuntimeTransport) -> None:
        self._t = transport

    async def get(self, key: str, default: Any = None) -> Any:
        return await self._t.memory_get(key, default)

    async def set(self, key: str, value: Any) -> None:
        await self._t.memory_set(key, value)

    async def all(self) -> dict[str, Any]:
        # 滤掉框架保留键（如 ctx.checkpoint 的 __chm_checkpoint__），不污染作者 memory 视图。
        return {
            k: v for k, v in (await self._t.memory_all()).items()
            if not (k.startswith("__chm_") and k.endswith("__"))
        }


class _KbProxy:
    """`ctx.kb` 的实现：把 search 转发给 transport（结构上满足 KbHandle）。"""

    def __init__(self, transport: RuntimeTransport) -> None:
        self._t = transport

    async def search(
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
        return await self._t.kb_search(
            query,
            kbs=kbs,
            top_k=top_k,
            min_score=min_score,
            mode=mode,
            rerank=rerank,
            expand=expand,
            hyde=hyde,
        )


def _usage_of(resp: Any) -> dict[str, int] | None:
    """从 LangChain message/chunk 抽 token 用量（duck-typed，不 import langchain）。"""
    meta = getattr(resp, "usage_metadata", None) or {}
    if not meta:
        rm = getattr(resp, "response_metadata", None) or {}
        meta = rm.get("token_usage", {}) if isinstance(rm, dict) else {}
    if not meta:
        return None
    prompt = meta.get("input_tokens") or meta.get("prompt_tokens") or 0
    completion = meta.get("output_tokens") or meta.get("completion_tokens") or 0
    total = meta.get("total_tokens") or (prompt + completion)
    if not total:
        return None
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(total),
    }


def _content_to_text(resp: Any) -> str:
    """从 LangChain message / chunk 取纯文本（content 可能是 str 或 block 列表）。"""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            if isinstance(b, str):
                parts.append(b)
            elif isinstance(b, dict) and isinstance(b.get("text"), str):
                parts.append(b["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def _docs_to_text(docs: Any) -> str:
    """把 ctx.kb.search 的结果（list[Doc]）拼成参考资料文本。"""
    out: list[str] = []
    for d in docs or []:
        text = getattr(d, "text", None)
        out.append(text if isinstance(text, str) else str(d))
    return "\n---\n".join(out)
