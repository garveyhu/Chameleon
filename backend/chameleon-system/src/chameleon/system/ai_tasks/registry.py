"""ai_tasks handler 注册表。

各业务域把自己的 AI 任务处理函数注册进来（task_type → handler）。ai_tasks 服务据此分发，
保持 ai_tasks 域对各业务域零反向依赖（业务域单向 import 本模块注册）。

handler 签名：async (session, input: dict) -> result: dict
- session：后台执行专用 AsyncSession（独立事务）。
- input：任务入参（如 {"run_ids": [...]}）。
- 返回：结果 dict（落 ai_tasks.result，前端反显）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

AiTaskHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]

AI_TASK_HANDLERS: dict[str, AiTaskHandler] = {}


def register_handler(task_type: str, fn: AiTaskHandler) -> None:
    """注册一个 AI 任务处理函数；task_type 对齐 aikit registry key。"""
    AI_TASK_HANDLERS[task_type] = fn


def has_handler(task_type: str) -> bool:
    return task_type in AI_TASK_HANDLERS
