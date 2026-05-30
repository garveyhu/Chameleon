"""注入 agent 范式桥——FakeAgent 用 build_graph()/build_runnable()，
BaseAgent.astream 经 core.base.bridge_registry 委托 integrations 的桥。
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _wire_agent_bridges() -> None:
    from chameleon.integrations.bridges import wire_agent_bridges

    wire_agent_bridges()
