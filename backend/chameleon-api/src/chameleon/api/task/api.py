"""task 模块 HTTP 路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.task import service
from chameleon.api.task.schemas import TaskItem
from chameleon.core.api.response import Result
from chameleon.data.infra.auth import CurrentApp, current_app
from chameleon.data.infra.db import get_session

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=Result[TaskItem])
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[TaskItem]:
    return Result.ok(await service.get_task(session, task_id, current_app=app))
