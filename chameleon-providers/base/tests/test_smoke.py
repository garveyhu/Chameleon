def test_import() -> None:
    import chameleon.providers.base

    assert chameleon.providers.base.__version__ == "0.1.0"
