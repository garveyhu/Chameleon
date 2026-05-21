def test_import() -> None:
    from chameleon.agents.echo_native import EchoNativeAgent

    md = EchoNativeAgent.get_metadata()
    assert md.id == "echo-native"
    assert "native" in md.tags
