def test_import() -> None:
    from chameleon.agents.example_echo_native import EchoNativeAgent

    md = EchoNativeAgent.get_metadata()
    assert md.id == "example-echo-native"
    assert "native" in md.tags
