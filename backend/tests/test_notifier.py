"""P23.C9: 通用 Notifier 组件（core/components/notifier）

从 eval_jobs 提升后的可复用注册表 + slack/webhook 渠道。
"""

from __future__ import annotations

import httpx

from chameleon.core.components.notifier import (
    NOTIFIER_REGISTRY,
    SlackNotifier,
    WebhookNotifier,
    get_notifier,
    list_notifier_kinds,
)

_WEBHOOK_URL = "https://example.test/hook"
_SLACK_URL = "https://hooks.slack.com/services/T0/B0/xxx"


def test_registry_has_builtin_kinds():
    assert set(list_notifier_kinds()) == {"slack", "webhook"}
    assert isinstance(get_notifier("slack"), SlackNotifier)
    assert isinstance(get_notifier("webhook"), WebhookNotifier)
    assert get_notifier("nope") is None
    # 单例：每次取同一实例
    assert get_notifier("slack") is NOTIFIER_REGISTRY["slack"]


async def test_webhook_send_payload_shape(respx_mock):
    route = respx_mock.post(_WEBHOOK_URL).mock(return_value=httpx.Response(200))
    sent = await WebhookNotifier().send(
        _WEBHOOK_URL, text="hello", payload={"k": "v"}
    )
    assert sent is True
    body = route.calls[0].request.content.decode()
    assert "chameleon" in body
    assert "hello" in body
    assert "\"k\"" in body or "'k'" in body


async def test_webhook_network_error_returns_false(respx_mock):
    respx_mock.post(_WEBHOOK_URL).mock(side_effect=httpx.ConnectError("boom"))
    sent = await WebhookNotifier().send(_WEBHOOK_URL, text="x")
    assert sent is False


async def test_slack_send_ok(respx_mock):
    respx_mock.post(_SLACK_URL).mock(
        return_value=httpx.Response(200, text="ok")
    )
    sent = await SlackNotifier().send(_SLACK_URL, text="hi", payload={"d": 1})
    assert sent is True


async def test_slack_non_200_false(respx_mock):
    respx_mock.post(_SLACK_URL).mock(return_value=httpx.Response(500))
    sent = await SlackNotifier().send(_SLACK_URL, text="hi")
    assert sent is False
