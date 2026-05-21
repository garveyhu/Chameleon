def test_import() -> None:
    import chameleon.providers.local as p

    assert p.__version__ == "0.1.0"
    assert p.PROVIDER.name == "local"
