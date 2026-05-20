def test_import() -> None:
    import chameleon.agents.echo as a

    assert a.__version__ == "0.1.0"
