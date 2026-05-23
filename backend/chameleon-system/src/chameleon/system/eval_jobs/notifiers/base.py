"""Notifier 抽象 ABC

约束：
- send() 必须 async + 短超时（< 10s），不能阻塞主事件循环
- 网络失败只 log + 返 False；alert pipeline 自己决定要不要重试 / 标记 sent
- 不持 db session；不写表
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Notifier(ABC):
    """alert 渠道抽象"""

    kind: str
    timeout: float = 5.0

    @abstractmethod
    async def send(
        self,
        target: str,
        *,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """发送告警

        Args:
            target: 渠道地址（slack webhook url / 通用 webhook url）
            text: 人类可读消息
            payload: 结构化补充字段（job_id / mean_score / delta_score 等）

        Returns:
            True = 已成功发出；False = 网络 / 配置错误
        """
        raise NotImplementedError
