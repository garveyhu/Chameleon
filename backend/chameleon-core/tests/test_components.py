"""components 子树 + base/ 单测"""

import secrets

from chameleon.core.base import (
    AgentConfigOption,
    AgentContext,
    AgentMetadata,
    BaseAgent,
    agent_router,
)
from chameleon.core.components import cache, embedding, llm, search_kb, vector
from chameleon.core.components.cache import CacheManager
from chameleon.core.components.llms import BaseLLM, ChatDeepSeek, ChatQwen
from chameleon.core.utils import model_to_dict

# ── inventory 顶层 callable ─────────────────────────────


def test_inventory_imports():
    """所有顶层符号都可 callable（无须实际调用）"""
    assert callable(llm)
    assert callable(embedding)
    assert callable(vector)
    assert callable(cache)
    assert callable(search_kb)


# ── cache 单例 ──────────────────────────────────────────


def test_cache_singleton():
    c1 = CacheManager()
    c2 = CacheManager()
    assert c1 is c2

    key = f"test-{secrets.token_hex(4)}"
    c1.set(key, "value", expire=5)
    assert c1.get(key) == "value"
    assert c2.get(key) == "value"
    c1.delete(key)
    assert c1.get(key, default="gone") == "gone"


# ── BaseLLM 子类层级 ────────────────────────────────────


def test_base_llm_subclasses():
    """ChatQwen / ChatDeepSeek 是 BaseLLM 子类"""
    assert issubclass(ChatQwen, BaseLLM)
    assert issubclass(ChatDeepSeek, BaseLLM)


def test_base_llm_parse_config_dict():
    """_parse_config 支持 dict 直传"""
    assert BaseLLM._parse_config({"top_p": 0.9}) == {"top_p": 0.9}


def test_base_llm_parse_config_sage_list_format():
    """与 sage 兼容：[{key, val}, ...] 格式"""
    sage_format = '[{"key": "top_p", "val": 0.9}, {"key": "max_tokens", "val": 1000}]'
    parsed = BaseLLM._parse_config(sage_format)
    assert parsed == {"top_p": 0.9, "max_tokens": 1000}


def test_base_llm_parse_config_empty():
    assert BaseLLM._parse_config(None) == {}
    assert BaseLLM._parse_config("") == {}


# ── BaseAgent 子类（含 agent_router 集成） ──────────────


class _FakeBaseAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="fake-base-agent",
            name="Fake",
            description="测试用",
            tags=["test"],
            config_options=[
                AgentConfigOption(
                    id="show_thinking",
                    type="toggle",
                    label="显示思考",
                    default=False,
                ),
            ],
        )

    @classmethod
    def build_graph(cls):
        from langgraph.graph import END, START, StateGraph
        from langgraph.graph.message import MessagesState

        async def echo(state):
            from langchain_core.messages import AIMessage

            return {"messages": [AIMessage(content="fake")]}

        sg = StateGraph(MessagesState)
        sg.add_node("e", echo)
        sg.add_edge(START, "e")
        sg.add_edge("e", END)
        return sg.compile()


def test_base_agent_metadata_to_dict():
    md = _FakeBaseAgent.get_metadata()
    d = md.to_dict()
    assert d["id"] == "fake-base-agent"
    assert d["name"] == "Fake"
    assert d["config_options"][0]["id"] == "show_thinking"
    assert d["config_options"][0]["type"] == "toggle"


def test_agent_router_register_and_list():
    agent_router.clear_for_test()
    agent_router.register(_FakeBaseAgent)
    assert agent_router.get("fake-base-agent") is _FakeBaseAgent
    metas = agent_router.list_metadata()
    assert any(m.id == "fake-base-agent" for m in metas)
    agent_router.clear_for_test()


# ── AgentContext ────────────────────────────────────────


def test_agent_context_helpers():
    ctx = AgentContext(
        app_id="app1",
        session_id="sess_xxx",
        app_config={"show_thinking": True, "k": 5},
        context_vars={"user_id": "u1"},
    )
    assert ctx.get_config("show_thinking") is True
    assert ctx.get_config("missing", default="d") == "d"
    assert ctx.get_var("user_id") == "u1"


# ── convert util ────────────────────────────────────────


def test_model_to_dict_basic():
    """ORM → dict 转换（用真实 ApiKey 模型）"""
    import secrets as _s

    from chameleon.core.models import ApiKey

    key = ApiKey(
        app_id="test-conv",
        name="t",
        key_hash="h" * 64,
        key_prefix="chm_test",
        scopes=["admin"],
        description=_s.token_hex(4),
    )
    d = model_to_dict(key, exclude=["key_hash"])
    assert d["app_id"] == "test-conv"
    assert d["scopes"] == ["admin"]
    assert "key_hash" not in d


# ── crypto（可选能力） ────────────────────────────────────


def test_crypto_encrypt_decrypt_roundtrip(monkeypatch):
    import base64

    from chameleon.core.utils.crypto import decrypt, encrypt, is_encrypted

    key = base64.urlsafe_b64encode(b"x" * 32).decode()
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", key)
    ct = encrypt("hello world")
    assert is_encrypted(ct)
    assert not is_encrypted("plain")
    assert decrypt(ct) == "hello world"


def test_crypto_get_or_decrypt(monkeypatch):
    import base64

    from chameleon.core.utils.crypto import encrypt, get_or_decrypt

    key = base64.urlsafe_b64encode(b"y" * 32).decode()
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", key)
    assert get_or_decrypt(None) is None
    assert get_or_decrypt("plain") == "plain"
    assert get_or_decrypt(encrypt("secret")) == "secret"
