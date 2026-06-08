"""T4-1：A2A 预算客户端注入漏洞修复验证。

外部可控的 req.context 不得通过 _ 前缀保留键篡改 A2A 预算 / 深度红线。
"""

from __future__ import annotations

from chameleon.providers.base import sanitize_context_vars


def test_sanitize_strips_reserved_prefix_keys():
    raw = {
        "foo": 1,
        "user_pref": "x",
        "_a2a_budget": 999_999_999,  # 客户端尝试注入
        "_a2a_depth": 0,
        "_internal": "y",
    }
    out = sanitize_context_vars(raw)
    assert out == {"foo": 1, "user_pref": "x"}
    assert "_a2a_budget" not in out
    assert "_a2a_depth" not in out


def test_none_and_empty():
    assert sanitize_context_vars(None) == {}
    assert sanitize_context_vars({}) == {}


def test_platform_budget_wins_over_client_injection():
    # 模拟 service 构造 context_vars：先 sanitize 客户端，再平台权威注入
    client = {"_a2a_budget": 999_999_999, "_a2a_depth": -1, "topic": "weather"}
    cvars = {
        **sanitize_context_vars(client),
        "_a2a_budget": 200_000,  # 平台权威值
        "_a2a_depth": 0,
    }
    assert cvars["_a2a_budget"] == 200_000  # 客户端 999999999 被剥后平台值生效
    assert cvars["_a2a_depth"] == 0
    assert cvars["topic"] == "weather"  # 业务键保留
