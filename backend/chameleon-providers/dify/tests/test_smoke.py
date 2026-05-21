def test_import() -> None:
    import chameleon.providers.dify as p

    assert p.__version__ == "0.1.0"
