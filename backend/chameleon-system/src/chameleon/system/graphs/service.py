"""graphs 业务 service —— CRUD + test-run

test-run 不落 graph_runs / graph_node_runs（仅 debug 用）；
正式跑 graph 走 PR #21 的 run_graph()，那个会写持久层 + 串联 trace tree。
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageResult
from chameleon.core.graph import GraphSpec, NodeContext
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.models import (
    Agent,
    ApiKey,
    App,
    EmbedConfig,
    Graph,
    GraphNodeRun,
    GraphRun,
)
from chameleon.system.api_key import service as api_key_service
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)
from chameleon.system.graphs.schemas import (
    CreateGraphRequest,
    GraphChatRequest,
    GraphDetail,
    GraphItem,
    GraphRunDetail,
    GraphRunItem,
    NodeRunItem,
    TestRunRequest,
    TestRunResult,
    UpdateGraphRequest,
    UpdateWebAppRequest,
    WebAppInfo,
)


async def list_graphs(session: AsyncSession) -> list[GraphItem]:
    rows = (
        (
            await session.execute(
                select(Graph)
                .where(Graph.deleted_at.is_(None))
                .order_by(Graph.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [GraphItem.model_validate(r) for r in rows]


async def get_graph(session: AsyncSession, graph_id: int) -> GraphDetail:
    row = await _load(session, graph_id)
    return GraphDetail.model_validate(row)


async def create_graph(
    session: AsyncSession, req: CreateGraphRequest
) -> GraphDetail:
    # 验 graph_key 唯一（防 DB UNIQUE 报错更清晰）
    dup = (
        await session.execute(
            select(Graph.id).where(Graph.graph_key == req.graph_key)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValidationError(message=f"graph_key 已存在: {req.graph_key}")

    # 校验 spec（构 GraphSpec + Orchestrator 实例化 node：data 校验也走了）
    _validate_spec(req.spec)

    row = Graph(
        graph_key=req.graph_key,
        name=req.name,
        description=req.description,
        kind=req.kind,
        spec=req.spec,
        enabled=True,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    return item


async def update_graph(
    session: AsyncSession, graph_id: int, req: UpdateGraphRequest
) -> GraphDetail:
    row = await _load(session, graph_id)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.kind is not None:
        row.kind = req.kind
    if req.spec is not None:
        _validate_spec(req.spec)
        row.spec = req.spec
    if req.enabled is not None:
        row.enabled = req.enabled
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    return item


async def delete_graph(session: AsyncSession, graph_id: int) -> None:
    """软删 —— graph_runs 历史保留（cascade 不触发，因为软删不删行）"""
    row = await _load(session, graph_id)
    row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()


async def publish_graph(
    session: AsyncSession, graph_id: int
) -> GraphDetail:
    """发布 draft → freeze 当前 spec 到 published_spec；published_version += 1

    红线（plan §2 P22）：published 版本 freeze；改要新 draft → publish 重走流程。
    本函数只做 freeze 当前 draft；如要"回滚到老版本"需另开端点（v1.x）。
    """
    row = await _load(session, graph_id)
    # 简单 freeze：从 draft spec 拷贝到 published_spec
    import copy

    row.published_spec = copy.deepcopy(row.spec)
    row.published_version = (row.published_version or 0) + 1
    row.published_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    logger.info(
        "graph published | id={} | version={}",
        row.id,
        row.published_version,
    )
    return item


async def publish_as_agent(
    session: AsyncSession, graph_id: int
) -> dict[str, Any]:
    """把工作流发布并暴露成一个可对话 agent（source='graph'）。

    - 若未发布则先 freeze published_spec；
    - upsert 一个 graph-backed Agent（按 graph_id 找已有，否则以 graph_key 为 agent_key 新建）；
    - reload agent registry，使其立即可从统一端点 /v1/agents/{key}/invoke 调用。
    """
    import copy

    row = await _load(session, graph_id)
    if not row.published_spec:
        row.published_spec = copy.deepcopy(row.spec)
        row.published_version = (row.published_version or 0) + 1
        row.published_at = datetime.now(timezone.utc)
        await session.flush()

    existing = (
        await session.execute(
            select(Agent).where(
                Agent.source == "graph",
                Agent.graph_id == row.id,
                Agent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.name = row.name
        existing.description = row.description
        existing.enabled = True
        agent = existing
    else:
        clash = (
            await session.execute(
                select(Agent).where(Agent.agent_key == row.graph_key)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ValidationError(
                message=(
                    f"agent_key 已被占用: {row.graph_key}"
                    "（请改 graph_key，或先处理同名 agent）"
                )
            )
        agent = Agent(
            agent_key=row.graph_key,
            name=row.name,
            description=row.description,
            source="graph",
            graph_id=row.id,
            enabled=True,
            workspace_id=getattr(row, "workspace_id", None),
        )
        session.add(agent)

    await session.flush()
    await session.refresh(agent)
    await session.commit()

    # 让新 agent 立即生效（registry 重读 DB + 预载 published_spec）
    from chameleon.providers.base.registry import reload_agent_registry

    await reload_agent_registry()

    logger.info(
        "graph published as agent | graph_id={} | agent_key={}",
        row.id,
        agent.agent_key,
    )
    return {"agent_key": agent.agent_key, "agent_id": agent.id}


def _gen_embed_key() -> str:
    return f"emb_{secrets.token_hex(12)}"


def _start_chat_cfg(spec: dict | None) -> tuple[str | None, list[str]]:
    """从 graph spec 的 start 节点取开场白 / 建议问题（喂给公开聊天页）。"""
    for n in (spec or {}).get("nodes") or []:
        if n.get("type") == "start":
            d = n.get("data") or {}
            sugg = d.get("suggested_questions") or []
            return d.get("opener") or None, [str(s) for s in sugg if s]
    return None, []


def _synced_behavior(
    existing: dict | None, opener: str | None, suggested: list[str]
) -> dict:
    """把开场白 / 建议问题同步进 behavior，保留其他键（如 placeholder）。"""
    b = dict(existing or {})
    if opener:
        b["welcome_message"] = opener
    else:
        b.pop("welcome_message", None)
    b["suggested_questions"] = suggested
    return b


async def _find_graph_agent(session: AsyncSession, graph_id: int) -> Agent | None:
    return (
        await session.execute(
            select(Agent).where(
                Agent.source == "graph",
                Agent.graph_id == graph_id,
                Agent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _find_embed(
    session: AsyncSession, agent_id: int
) -> EmbedConfig | None:
    return (
        (
            await session.execute(
                select(EmbedConfig)
                .where(
                    EmbedConfig.agent_id == agent_id,
                    EmbedConfig.deleted_at.is_(None),
                )
                .order_by(EmbedConfig.id)
            )
        )
        .scalars()
        .first()
    )


async def ensure_web_app(
    session: AsyncSession, graph_id: int
) -> WebAppInfo:
    """确保工作流有一个可公开访问的 Web App（基于 embed_config）。

    流程：未发布为智能体则先发布（建 agent + reload registry）→ 为其 agent
    找/建一个 App + EmbedConfig → 返回 embed_key（公开聊天页 /embed/{key}）。
    """
    row = await _load(session, graph_id)
    # commit 会让 ORM 对象过期，先把要用的字段取出来
    g_key, g_name, g_desc = row.graph_key, row.name, row.description
    g_ws = getattr(row, "workspace_id", None)
    opener, suggested = _start_chat_cfg(row.spec)  # start 节点的开场白 / 建议问题

    agent = await _find_graph_agent(session, graph_id)
    if agent is None:
        await publish_as_agent(session, graph_id)  # 建 agent + reload registry（内部 commit）
        agent = await _find_graph_agent(session, graph_id)
        if agent is None:
            raise BusinessError(
                ResultCode.InternalError, message="发布为智能体后仍未找到 agent"
            )
    agent_key, agent_id = agent.agent_key, agent.id

    ec = await _find_embed(session, agent_id)
    if ec is None:
        app_key = f"graph-{g_key}"
        app = (
            await session.execute(
                select(App).where(
                    App.app_key == app_key, App.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if app is None:
            app = App(app_key=app_key, name=g_name, workspace_id=g_ws)
            session.add(app)
            await session.flush()
            await session.refresh(app)
        ec = EmbedConfig(
            embed_key=_gen_embed_key(),
            name=g_name,
            description=g_desc,
            agent_id=agent_id,
            app_id=app.id,
            allowed_origins=["*"],  # 公开 Web App：任意 origin（embed_key 即访问凭据）
            behavior=_synced_behavior(None, opener, suggested),
            enabled=True,
            workspace_id=g_ws,
        )
        session.add(ec)
        await session.flush()
        await session.refresh(ec)
        info = _web_app_info(ec, agent_key)
        await session.commit()
        return info
    # 已存在：把开场白 / 建议问题同步到 behavior；老数据自愈 allowed_origins
    ec.behavior = _synced_behavior(ec.behavior, opener, suggested)
    if not ec.allowed_origins:
        ec.allowed_origins = ["*"]
    await session.flush()
    info = _web_app_info(ec, agent_key)
    await session.commit()
    return info


async def update_web_app(
    session: AsyncSession, graph_id: int, req: UpdateWebAppRequest
) -> WebAppInfo:
    """Web App 设置：写回 embed_config 的展示 / 行为配置。"""
    await ensure_web_app(session, graph_id)  # 确保存在
    agent = await _find_graph_agent(session, graph_id)
    if agent is None:
        raise BusinessError(ResultCode.Fail, message="尚未发布为智能体")
    ec = await _find_embed(session, agent.id)
    if ec is None:
        raise BusinessError(ResultCode.Fail, message="Web App 配置不存在")
    if req.name is not None:
        ec.name = req.name
    if req.description is not None:
        ec.description = req.description
    if req.ui_config is not None:
        ec.ui_config = req.ui_config
    if req.behavior is not None:
        ec.behavior = req.behavior
    if req.enabled is not None:
        ec.enabled = req.enabled
    await session.flush()
    info = _web_app_info(ec, agent.agent_key)
    await session.commit()
    return info


def _web_app_info(ec: EmbedConfig, agent_key: str) -> WebAppInfo:
    return WebAppInfo(
        id=ec.id,
        embed_key=ec.embed_key,
        agent_key=agent_key,
        name=ec.name,
        description=ec.description,
        ui_config=ec.ui_config or {},
        behavior=ec.behavior or {},
        enabled=ec.enabled,
    )


async def test_run(
    session: AsyncSession, graph_id: int, req: TestRunRequest
) -> TestRunResult:
    """跑一次但不落 graph_runs 表（仅 debug；正式 run 用 PR #21）"""
    row = await _load(session, graph_id)
    spec = _validate_spec(row.spec)

    ctx = NodeContext(
        request_id=f"testrun-{row.id}-{datetime.now(timezone.utc).timestamp():.0f}",
        graph_id=row.id,
        graph_run_id=0,  # 0 = 未持久化
        depth=0,
        started_at=datetime.now(timezone.utc),
    )
    orch = Orchestrator(spec)
    result = await orch.run(input=req.input, ctx=ctx)

    return TestRunResult(
        status=result.status.value,
        output=result.output,
        error=result.error,
        duration_ms=result.duration_ms,
        node_runs=[
            NodeRunItem(
                node_id=r.node_id,
                node_type=r.node_type,
                status=r.status.value,
                input=r.input,
                output=r.output,
                error=r.error,
                duration_ms=r.duration_ms,
            )
            for r in result.node_runs
        ],
    )


async def chat_stream(
    session: AsyncSession, graph_id: int, req: GraphChatRequest
) -> AsyncIterator[dict[str, Any]]:
    """对话式调试当前 draft：把 graph 当可对话 agent 多轮跑（临时会话，不落库）。

    复用 GraphProvider 的 input 组装 / 答案节点 / 事件翻译；spec 用 draft（不必先发布）。
    SSE chunk 形如 {"type": "delta"|"step"|"done"|"error", "data": {...}}。
    """
    from chameleon.providers.base.registry import PROVIDERS
    from chameleon.providers.base.types import AgentDef, InvokeContext, Message

    row = await _load(session, graph_id)
    # 提前校验 draft spec，给出干净错误（provider 内部也会校验）
    _validate_spec(row.spec)

    prov = PROVIDERS.get("graph")
    if prov is None:
        raise BusinessError(
            ResultCode.InternalError,
            message="graph provider 未注册（重启后端以加载 chameleon-providers/graph）",
        )

    adef = AgentDef(
        key=f"__draft__{row.graph_key}",
        provider="graph",
        config={"graph_id": row.id, "spec": row.spec},
    )
    history = [Message(role=h.role, content=h.content) for h in req.history]
    ctx = InvokeContext(
        agent_def=adef,
        input=req.message,
        history=history,
        context_vars={"conversation_vars": req.conversation_vars},
        # 一次调试对话一个 sess_*（前端跨轮携带）；与 request_id 形态不同，便于在日志按会话归类
        session_id=req.session_id or f"sess_dbg_{uuid.uuid4().hex[:12]}",
        app_id="__graph_debug__",
        request_id=f"graphdebug-{row.id}-{datetime.now(timezone.utc).timestamp():.0f}",
        stream=True,
    )
    async for ev in prov.stream(ctx):
        yield {"type": ev.type.value, "data": ev.data}


async def test_run_stream(
    session: AsyncSession, graph_id: int, req: TestRunRequest
) -> AsyncIterator[dict[str, Any]]:
    """流式跑一次（SSE）—— 不落 graph_runs；边执行边发 graph.node.* 事件

    与 test_run 同样不持久化（debug 用）；区别是返回 SSE 事件流（A1）。
    spec 加载 + 校验在首次迭代时用 route session 完成（FastAPI yield 依赖在
    StreamingResponse 发完前不关 session）；节点内部各自开独立 session。
    """
    row = await _load(session, graph_id)
    spec = _validate_spec(row.spec)

    ctx = NodeContext(
        request_id=f"testrun-{row.id}-{datetime.now(timezone.utc).timestamp():.0f}",
        graph_id=row.id,
        graph_run_id=0,  # 0 = 未持久化
        depth=0,
        started_at=datetime.now(timezone.utc),
    )
    orch = Orchestrator(spec)
    async for chunk in orch.run_streaming(input=req.input, ctx=ctx):
        yield chunk


# ── helpers ───────────────────────────────────────────────


async def _load(session: AsyncSession, graph_id: int) -> Graph:
    row = (
        await session.execute(
            select(Graph).where(
                Graph.id == graph_id, Graph.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph 不存在: {graph_id}"
        )
    return row


async def list_runs(
    session: AsyncSession,
    graph_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    session_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> PageResult[GraphRunItem]:
    """按 graph_id 分页列 runs（最新在前），支持状态 / 会话 / 时间范围筛选"""
    base = select(GraphRun).where(GraphRun.graph_id == graph_id)
    if status:
        base = base.where(GraphRun.status == status)
    if session_id:
        base = base.where(GraphRun.session_id.ilike(f"%{session_id}%"))
    if since is not None:
        base = base.where(GraphRun.created_at >= since)
    if until is not None:
        base = base.where(GraphRun.created_at <= until)
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(GraphRun.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=[GraphRunItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_run(session: AsyncSession, run_id: int) -> GraphRunDetail:
    row = (
        await session.execute(select(GraphRun).where(GraphRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph_run 不存在: {run_id}"
        )
    node_rows = (
        (
            await session.execute(
                select(GraphNodeRun)
                .where(GraphNodeRun.graph_run_id == run_id)
                .order_by(GraphNodeRun.started_at.asc(), GraphNodeRun.id.asc())
            )
        )
        .scalars()
        .all()
    )
    detail = GraphRunDetail.model_validate(row)
    detail.node_runs = [
        NodeRunItem(
            node_id=n.node_id,
            node_type=n.node_type,
            status=n.status,
            input=n.input,
            output=n.output,
            error=n.error,
            duration_ms=n.duration_ms or 0,
        )
        for n in node_rows
    ]
    return detail


def _validate_spec(spec: dict) -> GraphSpec:
    """spec dict → GraphSpec（结构 + 实例化 node 校验 data）"""
    try:
        gs = GraphSpec.model_validate(spec)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(message=f"spec 非法: {e}") from e
    try:
        # 实例化所有 node 跑 validate_data
        Orchestrator(gs)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(message=f"node config 校验失败: {e}") from e
    return gs


# ── 智能体级 API 密钥（编辑器「管理密钥」）──────────────────


async def _graph_agent(session: AsyncSession, graph_id: int) -> tuple[Graph, Agent]:
    """取 graph + 其已发布 Agent；未发布抛业务错误。"""
    g = (
        await session.execute(
            select(Graph).where(Graph.id == graph_id, Graph.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if g is None:
        raise BusinessError(ResultCode.Fail, message=f"graph 不存在: {graph_id}")
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.graph_id == graph_id, Agent.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise BusinessError(
            ResultCode.Fail,
            message="该工作流尚未发布为智能体，请先在编排页「发布为智能体」",
        )
    return g, agent


async def create_agent_key(
    session: AsyncSession, graph_id: int, name: str
) -> ApiKeyCreated:
    """为该 graph 的 agent 生成一个智能体级密钥（仅对该 agent 有效）。"""
    g, agent = await _graph_agent(session, graph_id)
    req = CreateApiKeyRequest(
        app_id=f"graph-{g.graph_key}",
        name=name or f"{g.name} 密钥",
        scope_type="agent",
        scope_ref=agent.agent_key,
    )
    return await api_key_service.create_api_key(session, req)


async def list_agent_keys(session: AsyncSession, graph_id: int) -> list[ApiKeyItem]:
    """列该 graph agent 的未吊销密钥（最新在前）。"""
    _, agent = await _graph_agent(session, graph_id)
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(
                    ApiKey.scope_type == "agent",
                    ApiKey.scope_ref == agent.agent_key,
                    ApiKey.revoked_at.is_(None),
                )
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [ApiKeyItem.model_validate(r) for r in rows]


async def revoke_agent_key(
    session: AsyncSession, graph_id: int, key_id: int
) -> ApiKeyItem:
    """吊销该 graph agent 名下的某个密钥（校验归属）。"""
    _, agent = await _graph_agent(session, graph_id)
    row = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id))
    ).scalar_one_or_none()
    if row is None or row.scope_type != "agent" or row.scope_ref != agent.agent_key:
        raise BusinessError(ResultCode.Fail, message="密钥不存在或不属于该智能体")
    return await api_key_service.revoke_api_key(session, key_id)
