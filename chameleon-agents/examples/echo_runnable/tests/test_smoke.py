def test_import() -> None:
    from chameleon.agents.example_echo_runnable import EchoRunnableAgent

    md = EchoRunnableAgent.get_metadata()
    assert md.id == "example-echo-runnable"
    assert "langchain" in md.tags
