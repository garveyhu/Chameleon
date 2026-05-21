"""task 模块 HTTP 路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.task import service
from chameleon.app.modules.task.schemas import TaskItem
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.api.response import Result

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=Result[TaskItem])
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[TaskItem]:
    return Result.ok(await service.get_task(session, task_id, current_app=app))
