"""评测域的 AI 任务 handler 注册（接入 ai_tasks 异步/缓存子系统）。

import 本模块即把 handler 注册进 ai_tasks registry（app 启动时 import 触发）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.system.ai_tasks.registry import register_handler
from chameleon.system.datasets import service as ds_service


async def _handle_compare_analysis(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """运行对比 AI 总结分析：input={"run_ids": [...]} → {"analysis": markdown}。"""
    run_ids = [int(x) for x in payload.get("run_ids", [])]
    result = await ds_service.analyze_comparison(session, run_ids)
    return {"analysis": result.analysis}


register_handler("eval.compare_analysis", _handle_compare_analysis)
