def test_import_app() -> None:
    from chameleon.app.main import app

    assert app.title == "Chameleon"


def test_health_route_registered() -> None:
    from chameleon.app.main import app

    paths = {r.path for r in app.routes}
    assert "/health" in paths
    assert "/ready" in paths
