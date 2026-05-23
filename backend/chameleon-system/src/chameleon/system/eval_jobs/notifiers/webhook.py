"""通用 Webhook 通知

POST 任意 JSON 到 target；接收方收到 `{ text, level, payload }` 结构。
2xx 视为成功。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from chameleon.system.eval_jobs.notifiers.base import Notifier


class WebhookNotifier(Notifier):
    kind = "webhook"

    async def send(
        self,
        target: str,
        *,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        body: dict[str, Any] = {
            "source": "chameleon-eval",
            "level": "alert",
            "text": text,
            "payload": payload or {},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    target,
                    json=body,
                    headers={"User-Agent": "chameleon-eval-notifier/1.0"},
                )
            ok = 200 <= resp.status_code < 300
            if not ok:
                logger.warning(
                    "webhook notifier non-2xx | status={} | body={!r}",
                    resp.status_code,
                    resp.text[:200],
                )
            return ok
        except httpx.TimeoutException:
            logger.warning("webhook notifier timeout | target={}", target)
            return False
        except httpx.RequestError as e:
            logger.warning("webhook notifier request error | err={}", e)
            return False
