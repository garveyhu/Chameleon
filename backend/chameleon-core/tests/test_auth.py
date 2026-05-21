import secrets
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from chameleon.core.infra.auth import (
    CurrentApp,
    current_app,
    generate_api_key,
    hash_api_key,
    require_scope,
)
from chameleon.core.infra.db import AsyncSessionLocal, get_session
from chameleon.core.api.exceptions import (
    BusinessError,
    PermissionDeniedError,
    ResultCode,
)
from chameleon.core.models import ApiKey, App


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("test-auth-%")))
        await s.execute(delete(App).where(App.app_key.like("test-auth-%")))
        await s.commit()


def test_hash_idempotent_and_deterministic() -> None:
    h1 = hash_api_key("chm_abc")
    h2 = hash_api_key("chm_abc")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_generate_api_key_format() -> None:
    plain, digest, prefix = generate_api_key()
    assert plain.startswith("chm_")
    assert len(plain) == 44  # chm_ + 40
    assert prefix == plain[:12]
    assert digest == hash_api_key(plain)


async def _make_test_key(*, scopes: list[str], revoked: bool = False) -> str:
    """落一条 api_key 行，返 plaintext。FK 前置：先建 App。"""
    plain, digest, prefix = generate_api_key()
    rand = secrets.token_hex(4)
    app_id = f"test-auth-{rand}"
    async with AsyncSessionLocal() as s:
        s.add(App(app_key=app_id, name=app_id))
        await s.flush()
        s.add(
            ApiKey(
                app_id=app_id,
                name="test",
                key_hash=digest,
                key_prefix=prefix,
                scopes=scopes,
                revoked_at=datetime.now(timezone.utc) if revoked else None,
            )
        )
        await s.commit()
    return plain


async def _resolve_current_app(authorization: str | None) -> CurrentApp:
    """绕过 FastAPI Depends 直调 current_app"""
    gen = get_session()
    session = await anext(gen)
    try:
        return await current_app(authorization=authorization, session=session)
    finally:
        try:
            await anext(gen)
        except StopAsyncIteration:
            pass


async def test_current_app_missing_header() -> None:
    with pytest.raises(BusinessError) as exc:
        await _resolve_current_app(None)
    assert exc.value.code == ResultCode.MissingApiKey


async def test_current_app_invalid_bearer() -> None:
    with pytest.raises(BusinessError) as exc:
        await _resolve_current_app("Bearer chm_invalid_key_does_not_exist")
    assert exc.value.code == ResultCode.InvalidApiKey


async def test_current_app_valid() -> None:
    plain = await _make_test_key(scopes=["admin"])
    app = await _resolve_current_app(f"Bearer {plain}")
    assert "admin" in app.scopes
    assert app.app_id.startswith("test-auth-")


async def test_current_app_revoked() -> None:
    plain = await _make_test_key(scopes=[], revoked=True)
    with pytest.raises(BusinessError) as exc:
        await _resolve_current_app(f"Bearer {plain}")
    assert exc.value.code == ResultCode.ApiKeyRevoked


async def test_require_scope_admin_pass() -> None:
    plain = await _make_test_key(scopes=["admin"])
    app = await _resolve_current_app(f"Bearer {plain}")
    guard = require_scope("admin")
    result = await guard(app=app)
    assert result is app


async def test_require_scope_admin_fail() -> None:
    plain = await _make_test_key(scopes=[])
    app = await _resolve_current_app(f"Bearer {plain}")
    guard = require_scope("admin")
    with pytest.raises(PermissionDeniedError) as exc:
        await guard(app=app)
    assert exc.value.code == ResultCode.AdminScopeRequired
