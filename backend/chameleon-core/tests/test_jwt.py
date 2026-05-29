"""JWT 双 token + 黑名单单测"""

from __future__ import annotations

import base64
import secrets
import time

import pytest

from chameleon.data.infra import redis as redis_infra
from chameleon.data.infra.jwt import (
    JwtInvalidToken,
    JwtNotConfigured,
    decode_token,
    decode_token_with_blacklist,
    encode_access_token,
    encode_refresh_token,
    generate_secret_b64,
    init_jwt,
    is_revoked,
    revoke_token,
)


def _set_secret(monkeypatch) -> None:
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    monkeypatch.setenv("CHAMELEON_JWT_SECRET", secret)


# ── 颁发 + 解码 ──────────────────────────────────────────────


def test_access_token_roundtrip(monkeypatch):
    _set_secret(monkeypatch)
    token, jti = encode_access_token(user_id=42, username="alice", roles=["admin"])
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["roles"] == ["admin"]
    assert payload["type"] == "access"
    assert payload["jti"] == jti


def test_refresh_token_roundtrip(monkeypatch):
    _set_secret(monkeypatch)
    token, jti = encode_refresh_token(user_id=42, username="alice", password_version=3)
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"
    assert payload["pwv"] == 3
    assert payload["jti"] == jti


def test_token_type_mismatch_rejected(monkeypatch):
    """expected_type 不符 → 抛"""
    _set_secret(monkeypatch)
    token, _ = encode_access_token(user_id=1, username="x")
    with pytest.raises(JwtInvalidToken):
        decode_token(token, expected_type="refresh")


def test_invalid_signature_rejected(monkeypatch):
    """B 服务 secret 不一样 → 验签失败"""
    _set_secret(monkeypatch)
    token, _ = encode_access_token(user_id=1, username="x")
    _set_secret(monkeypatch)  # 换 secret
    with pytest.raises(JwtInvalidToken):
        decode_token(token)


def test_expired_token_rejected(monkeypatch):
    """手动构造过期 token"""
    import jwt as pyjwt

    _set_secret(monkeypatch)
    from chameleon.data.infra.jwt import _get_secret

    expired = pyjwt.encode(
        {
            "sub": "1",
            "type": "access",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        },
        _get_secret(),
        algorithm="HS256",
    )
    with pytest.raises(JwtInvalidToken):
        decode_token(expired)


def test_malformed_token_rejected(monkeypatch):
    _set_secret(monkeypatch)
    with pytest.raises(JwtInvalidToken):
        decode_token("not-a-jwt-at-all")


# ── 黑名单 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_and_check(monkeypatch):
    _set_secret(monkeypatch)
    try:
        await redis_infra.ping()
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")

    _, jti = encode_access_token(user_id=1, username="x")
    assert await is_revoked(jti) is False
    await revoke_token(jti, ttl_seconds=60)
    assert await is_revoked(jti) is True


@pytest.mark.asyncio
async def test_decode_with_blacklist_rejects_revoked(monkeypatch):
    _set_secret(monkeypatch)
    try:
        await redis_infra.ping()
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")

    token, jti = encode_access_token(user_id=1, username="x")

    # 未吊销 → 通过
    payload = await decode_token_with_blacklist(token, expected_type="access")
    assert payload["jti"] == jti

    # 吊销后 → 拒绝
    await revoke_token(jti, ttl_seconds=60)
    with pytest.raises(JwtInvalidToken):
        await decode_token_with_blacklist(token, expected_type="access")


@pytest.mark.asyncio
async def test_revoke_ttl_zero_noop(monkeypatch):
    """TTL <= 0 时 revoke 不写入"""
    _set_secret(monkeypatch)
    try:
        await redis_infra.ping()
    except Exception as e:
        pytest.skip(f"Redis 不可用: {e}")
    _, jti = encode_access_token(user_id=1, username="x")
    await revoke_token(jti, ttl_seconds=0)
    assert await is_revoked(jti) is False


# ── init_jwt 启动期 ──────────────────────────────────────


def test_init_jwt_production_fail_fast(monkeypatch):
    monkeypatch.delenv("CHAMELEON_JWT_SECRET", raising=False)
    monkeypatch.setenv("CHAMELEON_ENV", "production")
    with pytest.raises(JwtNotConfigured):
        init_jwt()


def test_init_jwt_dev_default(monkeypatch):
    monkeypatch.delenv("CHAMELEON_JWT_SECRET", raising=False)
    monkeypatch.delenv("CHAMELEON_ENV", raising=False)
    init_jwt()
    assert "CHAMELEON_JWT_SECRET" in __import__("os").environ
    # demo key 能正常 encode + decode
    token, _ = encode_access_token(user_id=1, username="x")
    decode_token(token, expected_type="access")


def test_secret_too_short_rejected(monkeypatch):
    short = base64.urlsafe_b64encode(b"short").decode()
    monkeypatch.setenv("CHAMELEON_JWT_SECRET", short)
    with pytest.raises(JwtNotConfigured):
        encode_access_token(user_id=1, username="x")


def test_generate_secret_b64_yields_valid_secret():
    """工具：生成的 secret 解码后 ≥ 32 字节"""
    s = generate_secret_b64()
    decoded = base64.urlsafe_b64decode(s)
    assert len(decoded) >= 32
