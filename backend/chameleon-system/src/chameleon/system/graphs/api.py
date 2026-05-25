"""graphs HTTP 路由（/v1/admin/graphs）"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageResult, Result
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.api_key.schemas import ApiKeyCreated, ApiKeyItem
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.graphs import generator as graph_generator
from chameleon.system.graphs import human_input_service
from chameleon.system.graphs import runner as graph_runner
from chameleon.system.graphs import service as graph_service
from chameleon.system.graphs.schemas import (
    CreateAgentKeyRequest,
    CreateGraphRequest,
    GenerateGraphRequest,
    GraphChatRequest,
    GraphDetail,
    GraphItem,
    GraphRunDetail,
    GraphRunItem,
    GraphRunRequest,
    PendingInputItem,
    ResumeRunRequest,
    SuggestFollowupsRequest,
    TestRunRequest,
    TestRunResult,
    UpdateGraphRequest,
    UpdateWebAppRequest,
    WebAppInfo,
)

router = APIRouter(prefix="/v1/admin/graphs", tags=["admin:graphs"])


@router.get("", response_model=Result[list[GraphItem]])
async def list_graphs(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[GraphItem]]:
    items = await graph_service.list_graphs(session)
    return Result.ok(items)


@router.get("/pending", response_model=Result[list[PendingInputItem]])
async def list_pending(
    status: str = "pending",
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[PendingInputItem]]:
    """A6：列待人工回填的断点（status=pending/resolved/timeout）

    注：本路由须声明在 /{graph_id} 之前，否则 "pending" 会被当 graph_id 捕获。
    """
    items = await human_input_service.list_pending(session, status=status)
    return Result.ok(items)


@router.get("/{graph_id}", response_model=Result[GraphDetail])
async def get_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[GraphDetail]:
    item = await graph_service.get_graph(session, graph_id)
    return Result.ok(item)


@router.post("", response_model=Result[GraphDetail])
async def create_graph(
    req: CreateGraphRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    item = await graph_service.create_graph(session, req)
    return Result.ok(item)


@router.post("/generate", response_model=Result[GraphDetail])
async def generate_graph(
    req: GenerateGraphRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    """A4：自然语言描述 → LLM 生成 GraphSpec → 创建工作流并返回。"""
    spec = await graph_generator.generate_graph_spec(req.description)
    item = await graph_service.create_graph(
        session,
        CreateGraphRequest(
            graph_key=req.graph_key, name=req.name, description=req.description, spec=spec
        ),
    )
    return Result.ok(item)


@router.post("/suggest-followups", response_model=Result[list[str]])
async def suggest_followups(
    req: SuggestFollowupsRequest,
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[str]]:
    """A2：基于一轮问答生成 3 个建议追问。"""
    return Result.ok(await graph_generator.suggest_followups(req.question, req.answer))


@router.post("/{graph_id}/update", response_model=Result[GraphDetail])
async def update_graph(
    graph_id: int,
    req: UpdateGraphRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    item = await graph_service.update_graph(session, graph_id, req)
    return Result.ok(item)


@router.post("/{graph_id}/delete", response_model=Result[None])
async def delete_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:delete")),
) -> Result[None]:
    await graph_service.delete_graph(session, graph_id)
    return Result.ok(None)


@router.post(
    "/{graph_id}/publish", response_model=Result[GraphDetail]
)
async def publish_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    """P22.3：发布 draft → freeze published_spec；published_version += 1"""
    item = await graph_service.publish_graph(session, graph_id)
    return Result.ok(item)


@router.post("/{graph_id}/publish-as-agent", response_model=Result[dict])
async def publish_as_agent(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[dict]:
    """把工作流发布并暴露成可对话 agent（source='graph'），走统一 agent 端点。"""
    result = await graph_service.publish_as_agent(session, graph_id)
    return Result.ok(result)


@router.post("/{graph_id}/web-app", response_model=Result[WebAppInfo])
async def ensure_web_app(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[WebAppInfo]:
    """确保工作流有公开 Web App（embed），返回 embed_key（公开页 /embed/{key}）。"""
    return Result.ok(await graph_service.ensure_web_app(session, graph_id))


@router.post("/{graph_id}/web-app/update", response_model=Result[WebAppInfo])
async def update_web_app(
    graph_id: int,
    req: UpdateWebAppRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[WebAppInfo]:
    """Web App 设置：写回展示 / 行为配置（名称 / 描述 / 主题色 / 占位符等）。"""
    return Result.ok(await graph_service.update_web_app(session, graph_id, req))


@router.post(
    "/{graph_id}/test-run", response_model=Result[TestRunResult]
)
async def test_run(
    graph_id: int,
    req: TestRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
) -> Result[TestRunResult]:
    item = await graph_service.test_run(session, graph_id, req)
    return Result.ok(item)


@router.post("/{graph_id}/test-run/stream")
async def test_run_stream(
    graph_id: int,
    req: TestRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
):
    """SSE 流式 Test Run（A1）：边执行边推 graph.node.started/finished/failed

    不落 graph_runs（debug 用）；wire 事件见 SSEEventKind 的 GRAPH_* 成员。
    """
    return sse_response(
        graph_service.test_run_stream(session, graph_id, req),
        log_label="graphs:test-run-stream",
    )


@router.post("/{graph_id}/chat/stream")
async def chat_stream(
    graph_id: int,
    req: GraphChatRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
):
    """对话式调试当前 draft（把 graph 当可对话 agent 多轮跑，临时会话不落库）。

    SSE chunk：{"type": "delta"|"step"|"done"|"error", "data": {...}}。
    """
    return sse_response(
        graph_service.chat_stream(session, graph_id, req),
        log_label="graphs:chat-stream",
    )


@router.post("/{graph_id}/run", response_model=Result[GraphRunDetail])
async def run_graph(
    graph_id: int,
    req: GraphRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
) -> Result[GraphRunDetail]:
    """正式跑（持久化 graph_runs / graph_node_runs / call_logs，串到 trace tree）"""
    run = await graph_runner.run_graph(
        session, graph_id=graph_id, input=req.input
    )
    return Result.ok(GraphRunDetail.model_validate(run))


@router.post("/runs/{run_id}/resume", response_model=Result[GraphRunDetail])
async def resume_run(
    run_id: int,
    req: ResumeRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
) -> Result[GraphRunDetail]:
    """A6：人工回填后从断点恢复跑（可能再次暂停或终态收尾）"""
    run = await graph_runner.resume_run(session, run_id=run_id, value=req.value)
    return Result.ok(GraphRunDetail.model_validate(run))


@router.get("/{graph_id}/runs", response_model=Result[PageResult[GraphRunItem]])
async def list_runs(
    graph_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="success/failed/running/paused/..."),
    session_id: str | None = Query(None, description="会话标识（模糊匹配）"),
    since: datetime | None = Query(None, description="起始时间（含）"),
    until: datetime | None = Query(None, description="结束时间（含）"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[PageResult[GraphRunItem]]:
    return Result.ok(
        await graph_service.list_runs(
            session,
            graph_id,
            page=page,
            page_size=page_size,
            status=status,
            session_id=session_id,
            since=since,
            until=until,
        )
    )


@router.get("/runs/{run_id}", response_model=Result[GraphRunDetail])
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[GraphRunDetail]:
    item = await graph_service.get_run(session, run_id)
    return Result.ok(item)


# ── 智能体级 API 密钥（编辑器「管理密钥」）──────────────────


@router.get("/{graph_id}/api-keys", response_model=Result[list[ApiKeyItem]])
async def list_agent_keys(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[ApiKeyItem]]:
    return Result.ok(await graph_service.list_agent_keys(session, graph_id))


@router.post("/{graph_id}/api-keys", response_model=Result[ApiKeyCreated])
async def create_agent_key(
    graph_id: int,
    req: CreateAgentKeyRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[ApiKeyCreated]:
    return Result.ok(await graph_service.create_agent_key(session, graph_id, req.name))


@router.post("/{graph_id}/api-keys/{key_id}/revoke", response_model=Result[ApiKeyItem])
async def revoke_agent_key(
    graph_id: int,
    key_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[ApiKeyItem]:
    return Result.ok(await graph_service.revoke_agent_key(session, graph_id, key_id))
