def test_import() -> None:
    from chameleon.agents.echo_runnable import EchoRunnableAgent

    md = EchoRunnableAgent.get_metadata()
    assert md.id == "echo-runnable"
    assert "langchain" in md.tags
