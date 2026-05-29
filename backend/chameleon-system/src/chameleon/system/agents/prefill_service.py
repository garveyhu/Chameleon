"""应用配置预填：给定 agent_key，按 source 尽力解析 {model_code, system_prompt, kb_ids}。

Playground「关联应用」用——选一个已配好的应用，把它的模型 / 提示词 / 知识库作为本会话
默认值预填进运行设置，用户仍可覆盖（配置 = 应用默认 ⊕ 会话覆盖）。运行时 Playground 仍
是 model-direct，这里只做配置抽取，不改运行路径。各 source 可抽取程度不同：

- local @agent：模型取 default_model_code；KB 取 agent_kb_link；提示词写在代码里取不到。
- graph chatflow：从已发布 spec 的「回答 LLM 节点」取 model_name + system_prompt；KB 节点
  kb_key → KnowledgeBase.id。多节点时按回答节点启发式，可能不完整。
- graph workflow / 外部应用：无单一对话配置，prefillable=False，仅记录关联。
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import Agent, Graph, KnowledgeBase
from chameleon.system.agents import agent_kb_service


class AgentPrefillConfig(BaseModel):
    """应用 → 会话默认配置的抽取结果。"""

    agent_key: str
    name: str
    source: str
    graph_kind: str | None = None
    prefillable: bool = False
    model_code: str | None = None
    system_prompt: str | None = None
    kb_ids: list[int] = Field(default_factory=list)
    notes: str | None = None


async def _kb_ids_of_agent(session: AsyncSession, agent_id: int) -> list[int]:
    kbs = await agent_kb_service.list_linked_kbs(session, agent_id=agent_id)
    return [kb.id for kb in kbs]


def _resolve_answer_node_id(spec: dict) -> str | None:
    """回答节点启发式（轻量复刻 graph provider._resolve_answer_node）。

    优先 type=='answer' / data.is_answer；否则取指向 end 的边的 source，偏好 llm。
    """
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    for n in nodes:
        if n.get("type") == "answer" or (n.get("data") or {}).get("is_answer") is True:
            return n.get("id")
    end_ids = {n.get("id") for n in nodes if n.get("type") == "end"}
    if not end_ids:
        return None
    sources = [e.get("source") for e in edges if e.get("target") in end_ids]
    if not sources:
        return None
    by_id = {n.get("id"): n for n in nodes}
    for sid in sources:
        node = by_id.get(sid)
        if node is not None and node.get("type") == "llm":
            return sid
    return sources[0]


async def _kb_key_to_id(session: AsyncSession, kb_key: str) -> int | None:
    return (
        await session.execute(
            select(KnowledgeBase.id).where(
                KnowledgeBase.kb_key == kb_key,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _from_chatflow(
    session: AsyncSession, agent: Agent, graph: Graph
) -> AgentPrefillConfig:
    spec = graph.published_spec or graph.spec or {}
    nodes_by_id = {n.get("id"): n for n in (spec.get("nodes") or [])}
    ans_id = _resolve_answer_node_id(spec)
    ans_data = (nodes_by_id.get(ans_id) or {}).get("data") or {} if ans_id else {}
    kb_ids: list[int] = []
    for n in spec.get("nodes") or []:
        if n.get("type") == "kb":
            kk = (n.get("data") or {}).get("kb_key")
            if kk:
                kid = await _kb_key_to_id(session, kk)
                if kid is not None and kid not in kb_ids:
                    kb_ids.append(kid)
    return AgentPrefillConfig(
        agent_key=agent.agent_key,
        name=agent.name,
        source=agent.source,
        graph_kind="chatflow",
        prefillable=True,
        model_code=ans_data.get("model_name") or agent.default_model_code,
        system_prompt=ans_data.get("system_prompt"),
        kb_ids=kb_ids,
        notes="已从对话流的回答节点带出模型/提示词，KB 取自流程中的知识库节点（多节点时为最佳估计）。",
    )


async def build_prefill_config(
    session: AsyncSession, *, agent_key: str
) -> AgentPrefillConfig:
    """按 agent_key 解析可预填的会话默认配置。"""
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.agent_key == agent_key, Agent.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise BusinessError(ResultCode.Fail, message=f"应用不存在: {agent_key}")

    common = {"agent_key": agent.agent_key, "name": agent.name, "source": agent.source}

    if agent.source == "local":
        return AgentPrefillConfig(
            **common,
            prefillable=True,
            model_code=agent.default_model_code,
            kb_ids=await _kb_ids_of_agent(session, agent.id),
            notes="本地应用的提示词写在代码中，无法预填；已带出模型与关联知识库。",
        )

    if agent.source == "graph" and agent.graph_id is not None:
        graph = (
            await session.execute(
                select(Graph).where(
                    Graph.id == agent.graph_id, Graph.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if graph is None:
            return AgentPrefillConfig(
                **common, prefillable=False, notes="关联的工作流不存在，无法预填。"
            )
        if graph.kind != "chatflow":
            return AgentPrefillConfig(
                **common,
                graph_kind=graph.kind,
                prefillable=False,
                notes="工作流型应用无单一对话配置，仅记录关联，不预填。",
            )
        return await _from_chatflow(session, agent, graph)

    return AgentPrefillConfig(
        **common,
        prefillable=False,
        notes="外部应用配置在远端，无法预填，仅记录关联。",
    )
