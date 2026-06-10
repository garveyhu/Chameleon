"""agents HTTP 路由 (/v1/admin/agents)

操作：
- list / get（本地 + 外部一起列）
- create（仅 source != 'local'；local 由 namespace 扫描自动入表）
- update（所有 source 都可改 name/description/config/default_model_code/tags/icon）
- delete（local 拒绝；外部软删）
- enable / disable
- test：一次性 invoke 看返回（不入 call_logs）

字段语义说明
- default_model_code：「应用辅助调用模型」。对 local 既是业务也是辅助；对 graph
  仅作 followup / 自动标题 / 摘要等系统侧调用（业务调用走节点各自绑定的模型）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageResult, Result
from chameleon.data.infra.db import get_session
from chameleon.data.models import (
    Agent,
    AgentMemory,
    ApiKey,
    CallLog,
    EmbedConfig,
    Graph,
)
from chameleon.providers.base import AGENTS, reload_agent_registry
from chameleon.system.agents import agent_kb_service, prefill_service
from chameleon.system.agents.prefill_service import AgentPrefillConfig
from chameleon.system.api_key import service as api_key_service
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission

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
    # 关联工作流形态：chatflow / workflow（仅 source='graph' 有值）。
    # 供前端「应用目录」推导编排方式（对话编排 / 流程编排）。
    graph_kind: str | None = None
    config: dict | None = None
    default_model_code: str | None = None
    tags: list | None = None
    enabled: bool
    version: str | None = None
    icon: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentOption(BaseModel):
    """轻量选项（给 AgentPicker 下拉用）：分页 + 搜索 + 类别筛。"""

    id: int
    agent_key: str
    name: str
    source: str
    graph_kind: str | None = None
    icon: str | None = None


class CreateAgentRequest(BaseModel):
    agent_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    source: str = Field(pattern="^(dify|fastgpt|coze|comfyui)$")
    provider_id: int | None = None
    config: dict | None = None
    tags: list | None = None

    @model_validator(mode="after")
    def _check_comfyui_model(self) -> "CreateAgentRequest":
        if self.source == "comfyui" and not (self.config or {}).get("model_id"):
            raise ValueError("comfyui 应用必须绑定生图模型（config.model_id）")
        return self


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    default_model_code: str | None = None
    tags: list | None = None
    version: str | None = None
    # 头像 data URL；传空串 = 清除回默认图标
    icon: str | None = None


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


def _to_item(agent: Agent, graph_kind: str | None = None) -> AgentItem:
    """Agent ORM → AgentItem，附带关联工作流形态（source='graph' 时）。"""
    item = AgentItem.model_validate(agent)
    item.graph_kind = graph_kind
    return item


async def _graph_kind_of(session: AsyncSession, agent: Agent) -> str | None:
    """取 source='graph' 智能体所关联工作流的 kind；其他来源返回 None。"""
    if agent.source != "graph" or agent.graph_id is None:
        return None
    return (
        await session.execute(
            select(Graph.kind).where(Graph.id == agent.graph_id)
        )
    ).scalar_one_or_none()


# ── 路由 ──────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/agents", tags=["admin:agents"])


@router.get("", response_model=Result[list[AgentItem]])
async def list_agents(
    source: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[list[AgentItem]]:
    stmt = (
        select(Agent, Graph.kind)
        .outerjoin(Graph, Agent.graph_id == Graph.id)
        .where(Agent.deleted_at.is_(None))
        .order_by(Agent.source, Agent.agent_key)
    )
    if source:
        stmt = stmt.where(Agent.source == source)
    if enabled is not None:
        stmt = stmt.where(Agent.enabled.is_(enabled))
    rows = (await session.execute(stmt)).all()
    return Result.ok([_to_item(a, graph_kind) for a, graph_kind in rows])


@router.get("/options", response_model=Result[PageResult[AgentOption]])
async def list_agent_options(
    q: str | None = Query(default=None, description="名称 / key / 描述 模糊搜索"),
    category: str | None = Query(
        default=None,
        description="应用类别：local / graph-chatflow / graph-workflow / external",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[PageResult[AgentOption]]:
    """智能体选项分页 —— AgentPicker 用：搜索 + 类别筛 + 向下滚动加载下一页。"""
    base = (
        select(Agent, Graph.kind)
        .outerjoin(Graph, Agent.graph_id == Graph.id)
        .where(Agent.deleted_at.is_(None))
    )
    if category == "local":
        base = base.where(Agent.source == "local")
    elif category == "graph-chatflow":
        base = base.where(Agent.source == "graph", Graph.kind == "chatflow")
    elif category == "graph-workflow":
        base = base.where(Agent.source == "graph", Graph.kind == "workflow")
    elif category == "external":
        base = base.where(Agent.source.in_(("dify", "fastgpt", "coze")))
    if q:
        like = f"%{q}%"
        base = base.where(
            or_(
                Agent.name.ilike(like),
                Agent.agent_key.ilike(like),
                Agent.description.ilike(like),
            )
        )
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(
            base.order_by(Agent.source, Agent.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        AgentOption(
            id=a.id,
            agent_key=a.agent_key,
            name=a.name,
            source=a.source,
            graph_kind=gk,
            icon=a.icon,
        )
        for a, gk in rows
    ]
    return Result.ok(
        PageResult(items=items, total=int(total), page=page, page_size=page_size)
    )


@router.get(
    "/by-key/{agent_key}/prefill-config",
    response_model=Result[AgentPrefillConfig],
)
async def get_agent_prefill_config(
    agent_key: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentPrefillConfig]:
    """Playground「关联应用」预填：按 source 尽力解析模型/提示词/知识库默认配置。"""
    return Result.ok(
        await prefill_service.build_prefill_config(session, agent_key=agent_key)
    )


@router.get("/{agent_id}", response_model=Result[AgentItem])
async def get_agent(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentItem]:
    agent = await _get_or_404(session, agent_id)
    return Result.ok(_to_item(agent, await _graph_kind_of(session, agent)))


@router.post("", response_model=Result[AgentItem])
async def create_agent(
    req: CreateAgentRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentItem]:
    existing = (
        await session.execute(
            select(Agent).where(Agent.agent_key == req.agent_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"agent_key 已存在: {req.agent_key}")
    a = Agent(
        agent_key=req.agent_key,
        name=req.name,
        description=req.description,
        source=req.source,
        provider_id=req.provider_id,
        config=req.config,
        tags=req.tags,
        enabled=True,
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
    if req.default_model_code is not None:
        a.default_model_code = req.default_model_code or None
    if req.tags is not None:
        a.tags = req.tags
    if req.version is not None:
        a.version = req.version
    if req.icon is not None:
        a.icon = req.icon or None  # 空串 = 清除回默认图标
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
    original_key = a.agent_key
    before = {"agent_key": original_key, "name": a.name}
    now = datetime.now(timezone.utc)
    # 级联：撤销该应用的 API 密钥（scope=app / scope_ref=agent_key）+ 软删其嵌入配置；
    # 调用日志 / Trace 作为历史留存，不删。
    await session.execute(
        update(ApiKey)
        .where(
            ApiKey.scope_type == "app",
            ApiKey.scope_ref == original_key,
            ApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        update(EmbedConfig)
        .where(EmbedConfig.agent_id == a.id, EmbedConfig.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    a.deleted_at = now
    a.agent_key = f"__deleted_{a.id}_{original_key}"
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

    from chameleon.data.utils.snowflake import next_session_id
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
    # 仅代码应用（local）在此管 KB；graph 在画布配、外部在远端、生成应用无 KB
    agent = await _get_or_404(session, agent_id)
    if agent.source != "local":
        raise ValidationError(message="仅代码应用可在此关联知识库")
    kbs = await agent_kb_service.replace_linked_kbs(
        session, agent_id=agent_id, kb_ids=req.kb_ids
    )
    await session.commit()
    return Result.ok([LinkedKbItem.model_validate(k) for k in kbs])


# ── 多具名模型槽（agentkit @agent 声明 → 页面"关联模型"分槽绑定） ──


class ModelSlotItem(BaseModel):
    name: str
    label: str
    kind: str = "chat"  # 此槽需要的模型类型；前端据此过滤下拉
    optional: bool = False
    locked: bool = False
    default: str | None = None
    bound_code: str | None = None  # web 绑定的已配置模型 code（None=未绑=用默认）


class ConfiguredModelItem(BaseModel):
    code: str
    label: str
    kind: str  # chat/embedding/rerank/image/video，前端按槽 kind 过滤


class AgentModelSlotsResponse(BaseModel):
    slots: list[ModelSlotItem]
    models: list[ConfiguredModelItem]  # 已配置的启用模型（含 kind，下拉按槽 kind 过滤）


class UpdateModelBindingsRequest(BaseModel):
    bindings: dict[str, str] = Field(default_factory=dict)  # {槽名: code}；空=解绑


async def _build_slots_response(
    session: AsyncSession, agent: Agent
) -> AgentModelSlotsResponse:
    from chameleon.agentkit import declared_agents
    from chameleon.data.models.model_def import LLMModel

    manifest = declared_agents().get(agent.agent_key)
    bindings = agent.model_bindings or {}
    slots = [
        ModelSlotItem(
            name=s.name,
            label=s.label,
            kind=getattr(s, "kind", "chat"),
            optional=s.optional,
            locked=s.locked,
            default=s.default,
            bound_code=bindings.get(s.name),
        )
        for s in (manifest.models if manifest else [])
    ]
    # 返回全部启用模型（含 kind），前端按槽 kind 过滤下拉
    rows = (
        (
            await session.execute(
                select(LLMModel).where(
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    models = [
        ConfiguredModelItem(code=m.code, label=m.code, kind=m.kind) for m in rows
    ]
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
    from chameleon.data.models.model_def import LLMModel

    agent = await _get_or_404(session, agent_id)
    # 仅代码应用（local）有模型槽；graph 在画布配、外部在远端、生成应用绑单一模型
    if agent.source != "local":
        raise ValidationError(message="仅代码应用可在此绑定模型槽")
    manifest = declared_agents().get(agent.agent_key)
    slot_specs = {s.name: s for s in (manifest.models if manifest else [])}
    locked = {n for n, s in slot_specs.items() if s.locked}
    # code → kind 映射，绑定时校验「槽 kind == 模型 kind」（对话槽不能误绑生图模型）
    code_kind = dict(
        (
            await session.execute(
                select(LLMModel.code, LLMModel.kind).where(
                    LLMModel.enabled.is_(True),
                    LLMModel.deleted_at.is_(None),
                )
            )
        ).all()
    )

    clean: dict[str, str] = {}
    for slot, code in (req.bindings or {}).items():
        spec = slot_specs.get(slot)
        if spec is None:
            raise ValidationError(message=f"未声明的模型槽: {slot}")
        if slot in locked:
            raise ValidationError(message=f"模型槽 {slot} 已锁定，不可在页面修改")
        if not code:
            continue  # 空 = 解绑（用默认）
        if code not in code_kind:
            raise ValidationError(message=f"模型不存在或未启用: {code}")
        slot_kind = getattr(spec, "kind", "chat")
        if code_kind[code] != slot_kind:
            raise ValidationError(
                message=f"模型槽 {slot} 需要 {slot_kind} 类型模型，{code} 是 {code_kind[code]}"
            )
        clean[slot] = code

    agent.model_bindings = clean
    await session.commit()
    await reload_agent_registry()  # 让 AGENTS 重新注入新绑定
    return Result.ok(await _build_slots_response(session, agent))


# ── 关联工具（agentkit @agent(tools=[...]) 平台工具启停） ──


class AgentToolItem(BaseModel):
    tool_key: str
    description: str = ""
    enabled: bool = True


class AgentToolsResponse(BaseModel):
    tools: list[AgentToolItem]  # 该 agent 声明的平台工具可用集（含启停态）


class UpdateToolBindingsRequest(BaseModel):
    enabled: list[str] = Field(default_factory=list)  # 启用的 tool_key 子集


async def _build_tools_response(agent: Agent) -> AgentToolsResponse:
    from chameleon.agentkit import declared_agents
    from chameleon.integrations.tools import get_tool_class

    manifest = declared_agents().get(agent.agent_key)
    declared = list(manifest.tools) if manifest else []
    bindings = agent.tool_bindings  # None=全启用；列表=启用子集
    enabled_set = set(declared if bindings is None else bindings)
    tools = []
    for k in declared:
        cls = get_tool_class(k)
        tools.append(
            AgentToolItem(
                tool_key=k,
                description=(cls.description if cls else ""),
                enabled=k in enabled_set,
            )
        )
    return AgentToolsResponse(tools=tools)


@router.get("/{agent_id}/tools", response_model=Result[AgentToolsResponse])
async def get_agent_tools(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentToolsResponse]:
    agent = await _get_or_404(session, agent_id)
    return Result.ok(await _build_tools_response(agent))


@router.post(
    "/{agent_id}/tools/update", response_model=Result[AgentToolsResponse]
)
async def update_agent_tools(
    agent_id: int,
    req: UpdateToolBindingsRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentToolsResponse]:
    from chameleon.agentkit import declared_agents

    agent = await _get_or_404(session, agent_id)
    if agent.source != "local":
        raise ValidationError(message="仅代码应用可在此启停平台工具")
    manifest = declared_agents().get(agent.agent_key)
    declared = set(manifest.tools if manifest else [])
    for k in req.enabled:
        if k not in declared:
            raise ValidationError(message=f"未声明的平台工具: {k}")
    # 存启用子集（与声明集取交集，顺序按声明）
    agent.tool_bindings = [k for k in (manifest.tools if manifest else []) if k in set(req.enabled)]
    await session.commit()
    await reload_agent_registry()  # 让 AGENTS 重新注入新工具集
    return Result.ok(await _build_tools_response(agent))


# ── 配置 Schema（agentkit @agent(config=[Opt]) → 运营可调参数表单） ──


class ConfigOptionItem(BaseModel):
    key: str
    label: str
    type: str = "string"  # string / number / boolean / select
    choices: list[str] | None = None
    default: Any = None
    required: bool = False


class AgentConfigSchema(BaseModel):
    options: list[ConfigOptionItem]
    values: dict[str, Any]  # 当前已存的值（agents.config["opts"]）


class UpdateAgentConfigRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


def _build_config_schema(agent: Agent) -> AgentConfigSchema:
    from chameleon.agentkit import declared_agents

    manifest = declared_agents().get(agent.agent_key)
    options = [
        ConfigOptionItem(
            key=o.key,
            label=o.label,
            type=o.type,
            choices=o.choices,
            default=o.default,
            required=o.required,
        )
        for o in (manifest.config if manifest else [])
    ]
    values = dict((agent.config or {}).get("opts") or {})
    return AgentConfigSchema(options=options, values=values)


@router.get(
    "/{agent_id}/config-schema", response_model=Result[AgentConfigSchema]
)
async def get_agent_config_schema(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentConfigSchema]:
    agent = await _get_or_404(session, agent_id)
    return Result.ok(_build_config_schema(agent))


@router.post(
    "/{agent_id}/config/update", response_model=Result[AgentConfigSchema]
)
async def update_agent_config(
    agent_id: int,
    req: UpdateAgentConfigRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[AgentConfigSchema]:
    from chameleon.agentkit import declared_agents

    agent = await _get_or_404(session, agent_id)
    manifest = declared_agents().get(agent.agent_key)
    declared = {o.key for o in manifest.config} if manifest else set()

    clean = {k: v for k, v in (req.values or {}).items() if k in declared}
    # required 且无代码默认值的参数不允许空着保存——否则运行时 ctx.config 取值 KeyError
    if manifest:
        for o in manifest.config:
            if o.required and o.default is None:
                v = clean.get(o.key)
                if v is None or v == "":
                    raise ValidationError(message=f"参数 {o.key}（{o.label}）为必填")
    agent.config = {**(agent.config or {}), "opts": clean}
    await session.commit()
    await reload_agent_registry()  # 让 ctx.config 重新加载
    return Result.ok(_build_config_schema(agent))


# ── 高级能力（@agent 声明的 MCP / A2A / 沙箱 / durable）—— 运营侧只读可见 ──
#
# 代码声明 agent 的这些能力在代码里定，不在 UI 编辑；此端点把 manifest 透出供详情页展示，
# 让运营能看见「这个应用调了哪些远程/MCP、是否沙箱隔离、是否可恢复」。非 local 应用返空能力。


class McpServerInfo(BaseModel):
    name: str
    transport: str = "stdio"  # stdio / http / sse
    url: str | None = None


class GuardrailInfo(BaseModel):
    name: str  # 轨道名（no_injection / pii_redact / max_len / output_json_schema / 自定义）
    stage: str = "input"  # input / output
    action: str = "block"  # block / redact / retry / warn


class AgentCapabilities(BaseModel):
    is_local: bool  # 是否代码声明 agent（非 local 时下列均为默认/空）
    mcp_servers: list[McpServerInfo] = Field(default_factory=list)  # 消费的外部 MCP
    call_agents: list[str] = Field(default_factory=list)  # A2A allow-list（key 或远程 URL）
    sandboxed: bool = False  # docker 不可信隔离
    trust_tier: str = "internal"  # internal / untrusted
    durable: bool = False  # 可恢复执行 / 人在环 HITL
    # 能力增强（2026-06）：记忆 / 弹性 / 安全轨道——同为代码声明、运营侧只读可见
    working_memory: bool = False  # @agent(working_memory=Schema) 结构化槽自动注入
    observe_memory: bool = False  # @agent(observe_memory=True) observational 压缩
    retries: int = 0  # @agent(retries=N) ctx 瞬时错误退避重试
    guardrails: list[GuardrailInfo] = Field(default_factory=list)  # 安全轨道


def _build_capabilities(agent: Agent) -> AgentCapabilities:
    from chameleon.agentkit import declared_agents

    manifest = declared_agents().get(agent.agent_key) if agent.source == "local" else None
    if manifest is None:
        return AgentCapabilities(is_local=agent.source == "local")
    return AgentCapabilities(
        is_local=True,
        mcp_servers=[
            McpServerInfo(name=s.name, transport=s.transport, url=s.url)
            for s in (manifest.mcp_servers or [])
        ],
        call_agents=list(manifest.call_agents or []),
        sandboxed=manifest.sandboxed,
        trust_tier=manifest.trust_tier,
        durable=manifest.durable,
        working_memory=getattr(manifest, "working_memory", None) is not None,
        observe_memory=bool(getattr(manifest, "observe_memory", False)),
        retries=int(getattr(manifest, "retries", 0) or 0),
        guardrails=[
            GuardrailInfo(
                name=getattr(g, "name", "guardrail"),
                stage=getattr(g, "stage", "input"),
                action=getattr(g, "action", "block"),
            )
            for g in (getattr(manifest, "guardrails", None) or [])
        ],
    )


@router.get("/{agent_id}/capabilities", response_model=Result[AgentCapabilities])
async def get_agent_capabilities(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentCapabilities]:
    agent = await _get_or_404(session, agent_id)
    return Result.ok(_build_capabilities(agent))


# ── durable HITL 运营可见性：哪些会话的 run 正暂停等人工输入（运营侧掌握积压）──
#
# durable agent ctx.ask_human 暂停时，pending 落 AgentMemory（mkey=__chm_pending__，scope_ref=会话）。
# 此端点汇总该 agent 所有暂停中的 run + prompt，让运营无需进 playground/embed 即知 HITL 积压。
# 只读可见——回填续跑发生在终端用户所在场景（playground/embed），admin 代答语义不当故不在此提供。


class AgentPendingRun(BaseModel):
    scope_ref: str  # durable scope（= 会话 session_id / end_user_id）
    prompt: str
    call_index: int | None = None
    run_id: str | None = None
    updated_at: datetime


@router.get("/{agent_id}/pending-runs", response_model=Result[list[AgentPendingRun]])
async def get_agent_pending_runs(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[list[AgentPendingRun]]:
    agent = await _get_or_404(session, agent_id)
    rows = (
        (
            await session.execute(
                select(AgentMemory)
                .where(
                    AgentMemory.agent_key == agent.agent_key,
                    AgentMemory.mkey == "__chm_pending__",
                )
                .order_by(AgentMemory.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    candidates: list[tuple[AgentMemory, dict]] = []
    for r in rows:
        pending = (r.value or {}).get("v") if isinstance(r.value, dict) else None
        if isinstance(pending, dict) and pending.get("prompt"):
            candidates.append((r, pending))

    # 双保险（评审22 C2 健壮性）：journal 已有该 ask 点答案 = 已解决——即便 pending 未被清（旧数据
    # 或清除遗漏），也据 journal 过滤掉，保运营列表始终准确。journal 键含 run_id（per-run 唯一），
    # 故仅按 mkey 匹配即可消歧。
    def _jkey(p: dict) -> str | None:
        rid, ci = p.get("run_id"), p.get("call_index")
        return f"__chm_journal__{rid}__{ci}__" if rid is not None and ci is not None else None

    jkeys = {k for _, p in candidates if (k := _jkey(p))}
    resolved: set[str] = set()
    if jkeys:
        resolved = set(
            (
                await session.execute(
                    select(AgentMemory.mkey).where(
                        AgentMemory.agent_key == agent.agent_key,
                        AgentMemory.mkey.in_(jkeys),
                    )
                )
            )
            .scalars()
            .all()
        )

    out: list[AgentPendingRun] = []
    for r, pending in candidates:
        if (k := _jkey(pending)) and k in resolved:
            continue  # journal 有答案 = 已解决，不显示为待办
        out.append(
            AgentPendingRun(
                scope_ref=r.scope_ref,
                prompt=str(pending.get("prompt", "")),
                call_index=pending.get("call_index"),
                run_id=pending.get("run_id"),
                updated_at=r.updated_at,
            )
        )
    return Result.ok(out)


# ── 应用级 API 密钥（scope_type='app'，scope_ref = agent_key） ──
#
# 与编辑器里的「智能体密钥」同一作用域模型（graphs 域按 graph_id 入口），
# 这里按 agent_id 入口，供应用详情页「API」tab 用（本地 / 外部 / 图应用通用）。


class CreateAgentKeyRequest(BaseModel):
    name: str = Field(default="", max_length=128)


@router.get("/{agent_id}/api-keys", response_model=Result[list[ApiKeyItem]])
async def list_agent_api_keys(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[list[ApiKeyItem]]:
    agent = await _get_or_404(session, agent_id)
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(
                    ApiKey.scope_type == "app",
                    ApiKey.scope_ref == agent.agent_key,
                    ApiKey.revoked_at.is_(None),
                )
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return Result.ok([ApiKeyItem.model_validate(r) for r in rows])


@router.post("/{agent_id}/api-keys", response_model=Result[ApiKeyCreated])
async def create_agent_api_key(
    agent_id: int,
    req: CreateAgentKeyRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[ApiKeyCreated]:
    agent = await _get_or_404(session, agent_id)
    create_req = CreateApiKeyRequest(
        app_id=f"agent-{agent.agent_key}",
        name=req.name or f"{agent.name} 密钥",
        scope_type="app",
        scope_ref=agent.agent_key,
    )
    created = await api_key_service.create_api_key(session, create_req)
    await session.commit()
    return Result.ok(created)


@router.post(
    "/{agent_id}/api-keys/{key_id}/revoke", response_model=Result[ApiKeyItem]
)
async def revoke_agent_api_key(
    agent_id: int,
    key_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:write")),
) -> Result[ApiKeyItem]:
    agent = await _get_or_404(session, agent_id)
    row = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id))
    ).scalar_one_or_none()
    if row is None or row.scope_type != "app" or row.scope_ref != agent.agent_key:
        raise BusinessError(ResultCode.Fail, message="密钥不存在或不属于该应用")
    item = await api_key_service.revoke_api_key(session, key_id)
    await session.commit()
    return Result.ok(item)


# ── 调用概览（监测 tab）：按 agent_key 聚合 call_logs ──


class AgentOverviewItem(BaseModel):
    """单应用调用概览（按时间窗聚合 call_logs trace 根）"""

    window_hours: int
    total_calls: int
    success_rate: float  # 0~1
    total_tokens: int
    total_cost_usd: float  # 实际 CNY 元
    avg_duration_ms: float
    prev_total_calls: int  # 上一同长度周期，算 delta
    # 应用类型 —— 前端按此自适应指标（生成类应用无 token，显示生成数/成本）
    agent_source: str
    media_kind: str | None = None  # comfyui 生成应用：image / video


@router.get("/{agent_id}/overview", response_model=Result[AgentOverviewItem])
async def get_agent_overview(
    agent_id: int,
    hours: int = Query(default=24, ge=1, le=24 * 90),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("agents:read")),
) -> Result[AgentOverviewItem]:
    """该应用近 N 小时的调用次数 / 成功率 / tokens / 成本 / 平均时延。

    仅统计 trace 根（parent_id IS NULL），避免子 observation 重复计数。
    """
    agent = await _get_or_404(session, agent_id)
    now = datetime.now(timezone.utc)
    rf = now - timedelta(hours=hours)
    prev_from = rf - timedelta(hours=hours)

    base_where = (
        CallLog.agent_key == agent.agent_key,
        CallLog.parent_id.is_(None),
    )
    row = (
        await session.execute(
            select(
                func.count(CallLog.id).label("total"),
                func.count(CallLog.id)
                .filter(CallLog.success.is_(True))
                .label("succ"),
                func.coalesce(func.sum(CallLog.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(CallLog.cost_usd), 0).label("cost"),
                func.coalesce(func.avg(CallLog.duration_ms), 0.0).label("avg_dur"),
            ).where(*base_where, CallLog.created_at >= rf, CallLog.created_at <= now)
        )
    ).one()
    prev_total = (
        await session.execute(
            select(func.count(CallLog.id)).where(
                *base_where,
                CallLog.created_at >= prev_from,
                CallLog.created_at < rf,
            )
        )
    ).scalar_one()

    total = int(row.total or 0)
    # 生成类应用解析产物模态（image/video），前端据此把「总 Tokens」换成「生成数」
    media_kind = None
    if agent.source == "comfyui":
        from chameleon.data.models.model_def import LLMModel

        mid = (agent.config or {}).get("model_id")
        if mid:
            m = await session.get(LLMModel, int(mid))
            media_kind = m.kind if m else None
    return Result.ok(
        AgentOverviewItem(
            window_hours=hours,
            total_calls=total,
            success_rate=(int(row.succ or 0) / total) if total else 1.0,
            total_tokens=int(row.tokens or 0),
            total_cost_usd=float(row.cost or 0),
            avg_duration_ms=float(row.avg_dur or 0),
            prev_total_calls=int(prev_total or 0),
            agent_source=agent.source,
            media_kind=media_kind,
        )
    )
