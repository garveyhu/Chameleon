"""入站开放 A2A（POST /a2a/{key}）滥用面防御回归（安全审计补网）。

入站 A2A 是公开外部攻击面：depth 封顶防跨系统环递归 DoS、空消息/畸形/错方法早拒防烧 token。
这些防御此前无回归测试——一次错误重构可静默移除 depth 封顶→A2A 递归。本测钉死拒绝路径
（均在调真 agent 前早返回，故无需 DB / registry / 鉴权）。

注：预算注入（_a2a_budget/_a2a_depth 客户端篡改）的防护见 test_a2a_budget_isolation.py。
"""

from __future__ import annotations

import pytest

from chameleon.api.a2a.api import _A2A_MAX_DEPTH, message_send


def _body(*, method: str = "message/send", message=..., rpc_id: str = "1") -> dict:
    params = None if message is ... else {"message": message}
    return {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}


def _text_msg(text: str, *, depth: int | None = None) -> dict:
    msg: dict = {"parts": [{"kind": "text", "text": text}]}
    if depth is not None:
        msg["metadata"] = {"a2a_depth": depth}
    return msg


@pytest.mark.asyncio
async def test_rejects_over_max_depth() -> None:
    """跨系统深度超限 → 拒（防 A2A 环递归 DoS），不进真 agent 调用。"""
    body = _body(message=_text_msg("hi", depth=_A2A_MAX_DEPTH + 1))
    out = await message_send(key="any", body=body, _=None)
    assert out["error"]["code"] == -32000
    assert "深度超限" in out["error"]["message"]


@pytest.mark.asyncio
async def test_allows_at_max_depth_boundary_passes_depth_guard() -> None:
    """depth == 上限不被 depth 闸拒（边界）——验证用 > 而非 >=（误用 >= 会少放行一层合法调用）。"""
    body = _body(message=_text_msg("hi", depth=_A2A_MAX_DEPTH))
    # 放行后进 dev_call_agent（不存在的 agent 会返/抛错，但都不该是「深度超限」）。
    # 注：-32000 被复用于 depth 超限 + 包装下游错误，故按错误消息文案判，而非 code。
    try:
        out = await message_send(key="__nonexistent__", body=body, _=None)
    except Exception:  # noqa: BLE001 —— 进了后续真调用路径即说明过了 depth 闸
        return
    assert "深度超限" not in (out.get("error", {}).get("message", ""))


@pytest.mark.asyncio
async def test_rejects_empty_message() -> None:
    """空消息文本 → 拒（防空跑烧 token）。"""
    body = _body(message=_text_msg("   "))
    out = await message_send(key="any", body=body, _=None)
    assert out["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_rejects_unsupported_method() -> None:
    body = _body(method="tasks/cancel", message=_text_msg("hi"))
    out = await message_send(key="any", body=body, _=None)
    assert out["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_rejects_malformed_message() -> None:
    """params 缺 message / message 非对象 → Invalid params（非 500）。"""
    out = await message_send(key="any", body=_body(message=...), _=None)
    assert out["error"]["code"] == -32602
