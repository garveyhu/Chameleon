"""Eval alert notifier 注册表 —— P19.1 PR #31

注册式：kind -> Notifier 实例（单例，无状态）。
新增渠道：在 builtins/ 加文件 + import 到这里 _register。
"""

from __future__ import annotations

from chameleon.system.eval_jobs.notifiers.base import Notifier
from chameleon.system.eval_jobs.notifiers.slack import SlackNotifier
from chameleon.system.eval_jobs.notifiers.webhook import WebhookNotifier

NOTIFIER_REGISTRY: dict[str, Notifier] = {
    "slack": SlackNotifier(),
    "webhook": WebhookNotifier(),
}


def get_notifier(kind: str) -> Notifier | None:
    return NOTIFIER_REGISTRY.get(kind)


def list_notifier_kinds() -> list[str]:
    return sorted(NOTIFIER_REGISTRY.keys())


__all__ = [
    "Notifier",
    "NOTIFIER_REGISTRY",
    "get_notifier",
    "list_notifier_kinds",
]
