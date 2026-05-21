def test_import() -> None:
    from chameleon.agents.qwen_chat import QwenChatAgent

    md = QwenChatAgent.get_metadata()
    assert md.id == "qwen-chat"
    assert "qwen" in md.tags
