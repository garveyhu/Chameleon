"""Slack Incoming Webhook 通知

约定 target 是 `https://hooks.slack.com/services/T.../B.../...` 这种 URL。
发送格式：POST JSON `{"text": "..."}`。Slack 200 + body == "ok"。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from chameleon.system.eval_jobs.notifiers.base import Notifier


class SlackNotifier(Notifier):
    kind = "slack"

    async def send(
        self,
        target: str,
        *,
        text: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        body: dict[str, Any] = {"text": text}
        if payload:
            # 用 Slack 的 attachments 把结构化数据作为附件挂上
            body["attachments"] = [
                {
                    "color": "#dc3545",
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in payload.items()
                    ],
                }
            ]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(target, json=body)
            ok = resp.status_code == 200 and resp.text.strip().lower() in (
                "ok",
                "",
                '{"ok":true}',
            )
            if not ok:
                logger.warning(
                    "slack notifier returned non-ok | status={} | body={!r}",
                    resp.status_code,
                    resp.text[:200],
                )
            return ok
        except httpx.TimeoutException:
            logger.warning("slack notifier timeout | target={}", _redact(target))
            return False
        except httpx.RequestError as e:
            logger.warning(
                "slack notifier request error | target={} | err={}",
                _redact(target),
                e,
            )
            return False


def _redact(url: str) -> str:
    """slack webhook token 放在路径里，log 时只露 host 防泄漏"""
    if "://" not in url:
        return url
    return url.split("/services/")[0] + "/services/..."
