def test_import() -> None:
    from chameleon.agents.qwen_chat import handle

    m = handle.__agent_manifest__
    assert m.key == "qwen-chat"
    assert "qwen" in m.tags
    assert [s.name for s in m.models] == ["chat"]
