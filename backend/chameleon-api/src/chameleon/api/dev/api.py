"""agentkit dev 端点 HTTP 路由（/v1/dev/*）。

仅开发态放行：设了 `CHAMELEON_DEV_TOKEN` 才生效，且请求须带 `X-Dev-Token` 匹配；
未设 token（生产默认）→ 一律 404（隐藏端点存在）。handler 零业务，调 dev.service。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from chameleon.api.dev import service
from chameleon.api.dev.schemas import (
    DevDoc,
    DevKbSearchRequest,
    DevLlmRequest,
    DevLlmResponse,
    DevToolExecRequest,
    DevToolItem,
)
from chameleon.core.api.response import Result
from chameleon.core.config.env_settings import env_settings

router = APIRouter(prefix="/v1/dev", tags=["dev"])


async def require_dev_token(x_dev_token: str | None = Header(default=None)) -> None:
    """开发态闸门：未配置 token 或 header 不匹配 → 404（不暴露端点存在）。"""
    configured = env_settings.CHAMELEON_DEV_TOKEN
    if not configured or x_dev_token != configured:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/ping", response_model=Result[dict])
async def ping(_: None = Depends(require_dev_token)) -> Result[dict]:
    return Result.ok({"ok": True})


@router.post("/llm", response_model=Result[DevLlmResponse])
async def dev_llm(
    req: DevLlmRequest, _: None = Depends(require_dev_token)
) -> Result[DevLlmResponse]:
    out = await service.dev_llm(
        messages=req.messages,
        model=req.model,
        platform_tool_keys=req.platform_tool_keys,
        local_tool_schemas=req.local_tool_schemas,
    )
    return Result.ok(DevLlmResponse(**out))


@router.post("/kb/search", response_model=Result[list[DevDoc]])
async def dev_kb_search(
    req: DevKbSearchRequest, _: None = Depends(require_dev_token)
) -> Result[list[DevDoc]]:
    docs = await service.dev_kb_search(
        query=req.query, kbs=req.kbs, top_k=req.top_k, min_score=req.min_score,
        mode=req.mode, rerank=req.rerank, expand=req.expand, hyde=req.hyde,
    )
    return Result.ok([DevDoc(**d) for d in docs])


@router.post("/tools/exec", response_model=Result[dict])
async def dev_tool_exec(
    req: DevToolExecRequest, _: None = Depends(require_dev_token)
) -> Result[dict]:
    return Result.ok(await service.dev_exec_tool(name=req.name, args=req.args))


@router.get("/tools/list", response_model=Result[list[DevToolItem]])
async def dev_tool_list(_: None = Depends(require_dev_token)) -> Result[list[DevToolItem]]:
    return Result.ok([DevToolItem(**t) for t in service.dev_list_tools()])
