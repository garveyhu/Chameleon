"""通用 Notifier 组件（P23.C9）—— kind → Notifier 单例注册表

从 eval_jobs 提升到 core/components，供任何需要外发告警的场景复用（eval regression、
channel 健康、配额等）。无状态单例。

新增渠道：加一个 Notifier 子类文件 + import 到这里 _register。
"""

from __future__ import annotations

from chameleon.core.components.notifier.base import Notifier
from chameleon.core.components.notifier.slack import SlackNotifier
from chameleon.core.components.notifier.webhook import WebhookNotifier

NOTIFIER_REGISTRY: dict[str, Notifier] = {
    "slack": SlackNotifier(),
    "webhook": WebhookNotifier(),
}


def get_notifier(kind: str) -> Notifier | None:
    return NOTIFIER_REGISTRY.get(kind)


def list_notifier_kinds() -> list[str]:
    return sorted(NOTIFIER_REGISTRY.keys())


__all__ = [
    "NOTIFIER_REGISTRY",
    "Notifier",
    "SlackNotifier",
    "WebhookNotifier",
    "get_notifier",
    "list_notifier_kinds",
]
