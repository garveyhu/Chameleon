"""agent 高级能力透出（前端对齐 agentkit）：_build_capabilities 把 @agent 声明的 manifest
能力（mcp_servers/call_agents/sandboxed/trust_tier/durable）映射成只读响应，供详情页展示。
declared_agents() 的填充与 model-slots/tools/config 等已工作端点同机制（运行时 lifespan 注册）。
"""

from __future__ import annotations

from types import SimpleNamespace

import chameleon.agentkit as ak
import chameleon.system.agents.api as agents_api


def test_capabilities_local_agent_exposes_manifest(monkeypatch):
    mcp = SimpleNamespace(name="math", transport="http", url="http://x/mcp")
    manifest = SimpleNamespace(
        mcp_servers=[mcp], call_agents=["sub-a", "https://r/a2a/x"],
        sandboxed=True, trust_tier="untrusted", durable=True,
    )
    monkeypatch.setattr(ak, "declared_agents", lambda: {"k1": manifest})

    caps = agents_api._build_capabilities(SimpleNamespace(agent_key="k1", source="local"))
    assert caps.is_local and caps.sandboxed and caps.durable
    assert caps.trust_tier == "untrusted"
    assert caps.mcp_servers[0].name == "math" and caps.mcp_servers[0].url == "http://x/mcp"
    assert caps.call_agents == ["sub-a", "https://r/a2a/x"]


def test_capabilities_non_local_agent_is_empty(monkeypatch):
    monkeypatch.setattr(ak, "declared_agents", lambda: {})
    caps = agents_api._build_capabilities(SimpleNamespace(agent_key="g1", source="graph"))
    assert not caps.is_local
    assert caps.mcp_servers == [] and caps.call_agents == []
    assert not caps.sandboxed and not caps.durable and caps.trust_tier == "internal"


def test_capabilities_local_without_manifest_defaults(monkeypatch):
    """source=local 但 manifest 未注册（如 registry 未填充）→ is_local=True + 默认空能力。"""
    monkeypatch.setattr(ak, "declared_agents", lambda: {})
    caps = agents_api._build_capabilities(SimpleNamespace(agent_key="missing", source="local"))
    assert caps.is_local and caps.mcp_servers == [] and not caps.durable
