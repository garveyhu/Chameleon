"""agents HTTP 路由 (/v1/admin/agents)

操作：
- list / get（本地 + 外部一起列）
- create（仅 source != 'local'；local 由 namespace 扫描自动入表）
- update（本地仅能改 config / default_model_id / tags）
- delete（local 拒绝；外部软删）
- enable / disable
- test：一次性 invoke 看返回（不入 call_logs）
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Agent
from chameleon.core.models.workspace import DEFAULT_WORKSPACE_ID
from chameleon.providers.base import AGENTS, reload_agent_registry
from chameleon.system.agents import agent_kb_service
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import CurrentUser, require_permission

# ── DTO ────────────────────────────────────────────────────


class AgentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_key: str
    name: str
    description: str | None = None
    source: str
    provider_id: int | None = None
    local_class_path: str | None = None
    graph_id: int | None = None
    config: dict | None = None
    default_model_id: int | None = None
    tags: list | None = None
    enabled: bool
    version: str | None = None
    workspace_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CreateAgentRequest(BaseModel):
    agent_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    source: str = Field(pattern="^(dify|fastgpt|coze)$")
    provider_id: int | None = None
    config: dict | None = None
    tags: list | None = None


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    default_model_id: int | None = None
    tags: list | None = None
    version: str | None = None


class TestInvokeRequest(BaseModel):
    input: str = Field(min_length=1, max_length=8000)


class LinkedKbItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_key: str
    name: str
    description: str | None = None
    embedding_model: str
    embedding_dim: int


class UpdateLinkedKbsRequest(BaseModel):
    kb_ids: list[int]


# ── helpers ───────────────────────────────────────────────


async def _get_or_404(session: AsyncSession, agent_id: int) -> Agent:
    a = (
        await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if a is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"agent 不存在: {agent_id}"
        )
    return a


# ── 路由 ──────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/agents", tags=["admin:agents"])


@router.get("", response_model=Result[list[AgentItem]])
async def list_agents(
    source: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current: CurrentUser = Depends(require_permission("agents:read")),
) -> Result[list[AgentItem]]:
    stmt = (
        select(Agent)
        .where(Agent.deleted_at.is_(None))
        .order_by(Agent.source, Agent.agent_key)
    )
    if source:
        stmt = stmt.where(Agent.source == source)
    if enabled is not None:
        stmt = stmt.where(Agent.enabled.is_(enabled))
    stmt = _apply_workspace_filter(stmt, Agent, current)
    rows = (await session.execute(stmt)).scalars().all()
    return Result.ok([AgentItem.model_validate(a) for a in rows])


def _apply_workspace_filter(stmt, model, current: CurrentUser):
    """P19.3 工作区可见性过滤：
    - admin 未指定 ws → 不过滤
    - 指定 ws → 仅 workspace_id == ws；若包含 DEFAULT，允许老 NULL 行
    - 非 admin 多 ws → IN scope；含 DEFAULT 时同样收 NULL 行
    """
    ws_ids = current.workspace_filter_ids()
    if ws_ids is None:
        return stmt
    if DEFAULT_WORKSPACE_ID in ws_ids:
        return stmt.where(
            or_(
                model.workspace_id.in_(ws_ids),
                model.workspace_id.is_(None),
            )
        )
    return stmt.where(model.workspace_id.in_(ws_ids))


@router.get("/{agent_id}", response_model=Result[AgentItem])
async def get_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentItem]:
    return Result.ok(AgentItem.model_validate(await _get_or_404(session, agent_id)))


@router.post("", response_model=Result[AgentItem])
async def create_agent(
    req: CreateAgentRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    current: CurrentUser = Depends(require_permission("agents:write")),
) -> Result[AgentItem]:
    existing = (
        await session.execute(
            select(Agent).where(Agent.agent_key == req.agent_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"agent_key 已存在: {req.agent_key}")
    # P19.3：创建强制写 workspace_id —— admin 未指定 → DEFAULT
    ws_id = current.workspace_id if current.workspace_id is not None else DEFAULT_WORKSPACE_ID
    a = Agent(
        agent_key=req.agent_key,
        name=req.name,
        description=req.description,
        source=req.source,
        provider_id=req.provider_id,
        config=req.config,
        tags=req.tags,
        enabled=True,
        workspace_id=ws_id,
    )
    session.add(a)
    item = await _serialize_and_commit(session, a)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="agent.create",
        resource_type="agent",
        resource_id=item.id,
        after={"agent_key": item.agent_key, "name": item.name, "source": item.source},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


async def _serialize_and_commit(session: AsyncSession, a: Agent) -> AgentItem:
    """flush + refresh 拉所有 server_default 字段 → validate → commit → reload"""
    await session.flush()
    await session.refresh(a)
    item = AgentItem.model_validate(a)
    await session.commit()
    await reload_agent_registry()
    return item


@router.post("/{agent_id}/update", response_model=Result[AgentItem])
async def update_agent(
    agent_id: int,
    req: UpdateAgentRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentItem]:
    a = await _get_or_404(session, agent_id)
    if req.name is not None:
        a.name = req.name
    if req.description is not None:
        a.description = req.description
    if req.config is not None:
        a.config = req.config
    if req.default_model_id is not None:
        a.default_model_id = req.default_model_id
    if req.tags is not None:
        a.tags = req.tags
    if req.version is not None:
        a.version = req.version
    item = await _serialize_and_commit(session, a)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="agent.update",
        resource_type="agent",
        resource_id=item.id,
        after={"name": item.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{agent_id}/delete", response_model=Result[None])
async def delete_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("agents:delete")),
) -> Result[None]:
    a = await _get_or_404(session, agent_id)
    if a.source == "local":
        raise ValidationError(message="本地 agent 不可删除（仅可 disable）")
    before = {"agent_key": a.agent_key, "name": a.name}
    a.deleted_at = datetime.now(timezone.utc)
    a.agent_key = f"__deleted_{a.id}_{a.agent_key}"
    await session.flush()
    await session.commit()
    await reload_agent_registry()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="agent.delete",
        resource_type="agent",
        resource_id=agent_id,
        before=before,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


@router.post("/{agent_id}/enable", response_model=Result[AgentItem])
async def enable_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentItem]:
    a = await _get_or_404(session, agent_id)
    a.enabled = True
    return Result.ok(await _serialize_and_commit(session, a))


@router.post("/{agent_id}/disable", response_model=Result[AgentItem])
async def disable_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentItem]:
    a = await _get_or_404(session, agent_id)
    a.enabled = False
    return Result.ok(await _serialize_and_commit(session, a))


@router.post("/{agent_id}/test", response_model=Result[dict])
async def test_agent(
    agent_id: int,
    req: TestInvokeRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[dict]:
    """单次非流式 invoke，返完整 InvokeResult；不入 call_logs / conversations"""
    a = await _get_or_404(session, agent_id)
    if not a.enabled:
        raise ValidationError(message="agent 已禁用，请先 enable")
    if a.agent_key not in AGENTS:
        raise ValidationError(
            message=f"agent_key {a.agent_key} 不在 registry，请确认 reload"
        )

    from chameleon.core.utils.snowflake import next_session_id
    from chameleon.providers.base import PROVIDERS
    from chameleon.providers.base.types import InvokeContext

    agent_def = AGENTS[a.agent_key]
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider {agent_def.provider} 未注册",
        )
    ctx = InvokeContext(
        agent_def=agent_def,
        input=req.input,
        session_id=next_session_id(),
        app_id="__admin_test__",
        stream=False,
    )
    result = await provider.invoke(ctx)
    return Result.ok(result.model_dump())


# ── 关联 KB ───────────────────────────────────────────────


@router.get(
    "/{agent_id}/linked-kbs", response_model=Result[list[LinkedKbItem]]
)
async def list_agent_linked_kbs(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[list[LinkedKbItem]]:
    kbs = await agent_kb_service.list_linked_kbs(session, agent_id=agent_id)
    return Result.ok([LinkedKbItem.model_validate(k) for k in kbs])


@router.post(
    "/{agent_id}/linked-kbs/update",
    response_model=Result[list[LinkedKbItem]],
)
async def update_agent_linked_kbs(
    agent_id: int,
    req: UpdateLinkedKbsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[list[LinkedKbItem]]:
    kbs = await agent_kb_service.replace_linked_kbs(
        session, agent_id=agent_id, kb_ids=req.kb_ids
    )
    await session.commit()
    return Result.ok([LinkedKbItem.model_validate(k) for k in kbs])


# ── 多具名模型槽（agentkit @agent 声明 → 页面"关联模型"分槽绑定） ──


class ModelSlotItem(BaseModel):
    name: str
    label: str
    optional: bool = False
    locked: bool = False
    default: str | None = None
    bound_code: str | None = None  # web 绑定的已配置模型 code（None=未绑=用默认）


class ConfiguredModelItem(BaseModel):
    code: str
    label: str


class AgentModelSlotsResponse(BaseModel):
    slots: list[ModelSlotItem]
    models: list[ConfiguredModelItem]  # 可选的已配置 chat 模型（下拉用）


class UpdateModelBindingsRequest(BaseModel):
    bindings: dict[str, str] = Field(default_factory=dict)  # {槽名: code}；空=解绑


async def _build_slots_response(
    session: AsyncSession, agent: Agent
) -> AgentModelSlotsResponse:
    from chameleon.agentkit import declared_agents
    from chameleon.core.models.model_def import LLMModel

    manifest = declared_agents().get(agent.agent_key)
    bindings = agent.model_bindings or {}
    slots = [
        ModelSlotItem(
            name=s.name,
            label=s.label,
            optional=s.optional,
            locked=s.locked,
            default=s.default,
            bound_code=bindings.get(s.name),
        )
        for s in (manifest.models if manifest else [])
    ]
    rows = (
        (
            await session.execute(
                select(LLMModel).where(
                    LLMModel.kind == "chat",
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    models = [ConfiguredModelItem(code=m.code, label=m.code) for m in rows]
    return AgentModelSlotsResponse(slots=slots, models=models)


@router.get(
    "/{agent_id}/model-slots", response_model=Result[AgentModelSlotsResponse]
)
async def get_agent_model_slots(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentModelSlotsResponse]:
    agent = await _get_or_404(session, agent_id)
    return Result.ok(await _build_slots_response(session, agent))


@router.post(
    "/{agent_id}/model-bindings/update",
    response_model=Result[AgentModelSlotsResponse],
)
async def update_agent_model_bindings(
    agent_id: int,
    req: UpdateModelBindingsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentModelSlotsResponse]:
    from chameleon.agentkit import declared_agents
    from chameleon.core.models.model_def import LLMModel

    agent = await _get_or_404(session, agent_id)
    manifest = declared_agents().get(agent.agent_key)
    declared = {s.name for s in manifest.models} if manifest else set()
    locked = {s.name for s in (manifest.models if manifest else []) if s.locked}
    valid_codes = set(
        (
            await session.execute(
                select(LLMModel.code).where(
                    LLMModel.kind == "chat",
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    clean: dict[str, str] = {}
    for slot, code in (req.bindings or {}).items():
        if slot not in declared:
            raise ValidationError(message=f"未声明的模型槽: {slot}")
        if slot in locked:
            raise ValidationError(message=f"模型槽 {slot} 已锁定，不可在页面修改")
        if not code:
            continue  # 空 = 解绑（用默认）
        if code not in valid_codes:
            raise ValidationError(message=f"模型不存在或未启用: {code}")
        clean[slot] = code

    agent.model_bindings = clean
    await session.commit()
    await reload_agent_registry()  # 让 AGENTS 重新注入新绑定
    return Result.ok(await _build_slots_response(session, agent))
