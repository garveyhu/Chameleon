def test_import() -> None:
    from chameleon.agents.example_echo_langgraph import EchoLangGraphAgent

    md = EchoLangGraphAgent.get_metadata()
    assert md.id == "example-echo-langgraph"
    assert "example" in md.tags
