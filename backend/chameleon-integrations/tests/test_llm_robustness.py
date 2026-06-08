"""LLM 鲁棒性默认（评审12 错误路径）：客户端超时 + transient 重试退避，且可覆盖/env 调。

langchain ChatOpenAI 裸默认 timeout=None（hung 上游无限阻塞）。这里固化"必有超时 + 必有重试"
不变量，防回归（评审12 指出此前 code 层无显式处理）。
"""

from __future__ import annotations

import importlib

import httpx
import pytest
import respx

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


def _openai_ok(content: str) -> dict:
    return {
        "id": "c", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
async def test_retry_on_429_actually_retries_behavior():
    """真退避行为（评审13：此前只验字段未验行为）：上游先返 429(Retry-After:0) 再 200，断言
    底层 OpenAI SDK 真重试——发生 2 次 HTTP 调用且最终成功，而非首个 429 即失败。"""
    calls = {"n": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            # Retry-After:0 → SDK 立即重试（不拖慢测试）；429 在 SDK _should_retry 白名单内
            return httpx.Response(429, headers={"retry-after": "0"},
                                  json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json=_openai_ok("ok"))

    with respx.mock:
        respx.post(url__regex=r".*/chat/completions").mock(side_effect=_responder)
        m = BaseLLM(model="gpt-4o-mini", api_key="sk-test",
                    api_base="http://test/v1", max_retries=2)
        resp = await m.ainvoke("hi")

    assert calls["n"] == 2, f"应真重试一次（429→200），实际 HTTP 调用 {calls['n']} 次"
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_no_retry_when_disabled_429_fails_fast():
    """对照：max_retries=0 时 429 不重试、立即失败（证重试确由 max_retries 驱动，非偶然）。"""
    calls = {"n": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with respx.mock:
        respx.post(url__regex=r".*/chat/completions").mock(side_effect=_responder)
        m = BaseLLM(model="gpt-4o-mini", api_key="sk-test",
                    api_base="http://test/v1", max_retries=0)
        with pytest.raises(Exception):  # noqa: B017,PT011 —— 429 直接上抛
            await m.ainvoke("hi")

    assert calls["n"] == 1, f"max_retries=0 应只调 1 次即失败，实际 {calls['n']} 次"
