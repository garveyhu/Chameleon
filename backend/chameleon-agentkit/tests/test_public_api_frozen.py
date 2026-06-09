"""内部 API 契约冻结门禁（T3-6）：把「chameleon.agentkit 导出面只增不改」从人工验证升级为机器
强制。chameleon.agentkit 是平台内部 SDK，其导出面是站内所有 agent 依赖的稳定契约——移除/改名
冻结名 = 破坏性变更（须协调所有内部 agent + 显式改基线，评审会拦），即失败；新增放行。配 .github
CI 后，任何无意破坏该契约的改动都会被自动挡下。

基线快照锚定于 feat/agentkit-capabilities（2026-06）。要扩导出面：把新增名加进对应集合（增量）。
要移除/改名（罕见、破坏性）：同步更新基线，并在 PR 说明破坏性变更 + 内部迁移方式。
"""

from __future__ import annotations

import inspect

import chameleon.agentkit as ak

# 模块顶层导出（`from chameleon.agentkit import X`）的冻结集
FROZEN_ALL = {
    "AgentManifest", "AgentMetadata", "AgentPaused", "AgentRun", "BaseAgent", "Doc",
    "KbHandle", "McpServerConfig", "MediaHandle", "MediaResult", "MemoryHandle", "Message",
    "ModelSlot", "Opt", "RuntimeTransport", "StreamEvent", "StreamEventType", "ToolSpec",
    "agent", "declared_agents", "tool",
}

# 作者写 handle(ctx) 时用的 ctx（AgentRun）公共方法/属性面——这是真正的作者 API 契约
FROZEN_CTX = {
    "ask_human", "call_agent", "checkpoint", "complete", "emit", "gather", "handoff",
    "kb", "llm", "media", "memory", "restore", "route", "run_with_tools", "span",
    "stream", "wrap",
}

# 关键 ctx 方法的冻结必备参数名（防悄悄删/改参数破坏既有调用；新增带默认值的参数放行）
FROZEN_SIGNATURES = {
    "complete": {"user"},           # ctx.complete(*, user=..., ...)
    "stream": {"user"},
    "ask_human": {"prompt"},        # ctx.ask_human(prompt, ...)
    "call_agent": {"target", "input"},
    "route": {"query", "agents"},
}


def test_module_public_surface_frozen():
    """`__all__` 不得移除冻结公共名（破坏性），新增放行。"""
    missing = FROZEN_ALL - set(ak.__all__)
    assert not missing, f"chameleon.agentkit.__all__ 移除了冻结公共名（破坏性！须走 major）：{missing}"


def test_frozen_names_importable():
    """冻结公共名必须真能从顶层取到（防「在 __all__ 列着但实际删了」）。"""
    broken = [n for n in FROZEN_ALL if not hasattr(ak, n)]
    assert not broken, f"冻结公共名在 __all__ 但 import 不到（破坏性）：{broken}"


def test_ctx_public_surface_frozen():
    """ctx（AgentRun）作者面方法不得移除/改名（破坏性）。"""
    current = {n for n in dir(ak.AgentRun) if not n.startswith("_")}
    missing = FROZEN_CTX - current
    assert not missing, f"AgentRun(ctx) 移除了冻结公共方法（破坏性！）：{missing}"


def test_ctx_required_params_frozen():
    """关键 ctx 方法的冻结必备参数不得删/改名（删 = 破坏既有调用）；新增带默认参数放行。"""
    for method, required in FROZEN_SIGNATURES.items():
        params = set(inspect.signature(getattr(ak.AgentRun, method)).parameters)
        missing = required - params
        assert not missing, f"AgentRun.{method} 移除了冻结必备参数（破坏性）：{missing}"
