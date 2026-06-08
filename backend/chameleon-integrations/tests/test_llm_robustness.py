"""LLM 鲁棒性默认（评审12 错误路径）：客户端超时 + transient 重试退避，且可覆盖/env 调。

langchain ChatOpenAI 裸默认 timeout=None（hung 上游无限阻塞）。这里固化"必有超时 + 必有重试"
不变量，防回归（评审12 指出此前 code 层无显式处理）。
"""

from __future__ import annotations

import importlib

from chameleon.integrations.llms.base import BaseLLM


def test_default_timeout_and_retries_set():
    """裸构造即带客户端超时 + 重试退避——防 hung 上游永久阻塞、transient 错误自动退避。"""
    m = BaseLLM(model="gpt-4o-mini", api_key="sk-test", api_base="http://x/v1")
    assert m.request_timeout is not None and m.request_timeout > 0  # 不再是 None（永久阻塞）
    assert m.max_retries >= 1  # 显式重试退避


def test_kwargs_override_robustness_defaults():
    """显式 kwargs 覆盖默认（运营/作者可按上游特性调）。"""
    m = BaseLLM(model="x", api_key="k", max_retries=5, request_timeout=10)
    assert m.max_retries == 5
    assert m.request_timeout == 10.0


def test_env_tunes_defaults(monkeypatch):
    """env 调全局默认（CHAMELEON_LLM_TIMEOUT / _MAX_RETRIES），reload 模块后生效。"""
    monkeypatch.setenv("CHAMELEON_LLM_TIMEOUT", "123")
    monkeypatch.setenv("CHAMELEON_LLM_MAX_RETRIES", "7")
    import chameleon.integrations.llms.base as base_mod

    importlib.reload(base_mod)
    try:
        m = base_mod.BaseLLM(model="x", api_key="k")
        assert m.request_timeout == 123.0
        assert m.max_retries == 7
    finally:
        monkeypatch.undo()
        importlib.reload(base_mod)  # 还原模块级常量，免污染其它测试
