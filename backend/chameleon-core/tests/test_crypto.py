"""AES-256-GCM 加密工具单测

覆盖：
- 加密/解密往返
- nonce 唯一（同明文加密两次得到不同密文）
- 错误 key 解密失败
- key 长度校验
- init_crypto 在 dev / production 两种模式下的行为
"""

from __future__ import annotations

import base64
import os
import secrets

import pytest

from chameleon.data.utils.crypto import (
    CryptoNotConfigured,
    _get_key,
    decrypt,
    encrypt,
    get_or_decrypt,
    init_crypto,
    is_encrypted,
)


def _gen_key_b64() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", _gen_key_b64())
    plaintext = "sk-secretkey-12345"
    ct = encrypt(plaintext)
    assert is_encrypted(ct)
    assert not is_encrypted(plaintext)
    assert decrypt(ct) == plaintext


def test_nonce_uniqueness(monkeypatch):
    """同明文加密两次必须得到不同密文（nonce 随机）"""
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", _gen_key_b64())
    plaintext = "hello"
    ct1 = encrypt(plaintext)
    ct2 = encrypt(plaintext)
    assert ct1 != ct2
    assert decrypt(ct1) == decrypt(ct2) == plaintext


def test_wrong_key_decrypt_fails(monkeypatch):
    """同明文用 A key 加密，用 B key 解密必须失败"""
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", _gen_key_b64())
    ct = encrypt("hello")

    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", _gen_key_b64())
    with pytest.raises(Exception):
        decrypt(ct)


def test_invalid_key_length_raises(monkeypatch):
    """非 16/24/32 字节 key 抛 CryptoNotConfigured"""
    short_key = base64.urlsafe_b64encode(b"short").decode()
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", short_key)
    with pytest.raises(CryptoNotConfigured):
        _get_key()


def test_invalid_base64_raises(monkeypatch):
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", "not-valid-base64!!!  ")
    with pytest.raises(CryptoNotConfigured):
        _get_key()


def test_get_or_decrypt(monkeypatch):
    """智能：已加密的解，未加密的原样返"""
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", _gen_key_b64())
    assert get_or_decrypt(None) is None
    assert get_or_decrypt("plain-text") == "plain-text"
    ct = encrypt("encrypted-text")
    assert get_or_decrypt(ct) == "encrypted-text"


def test_init_crypto_production_fail_fast(monkeypatch):
    """production 模式 + 无 key → 启动 fail-fast"""
    monkeypatch.delenv("CHAMELEON_CRYPTO_KEY", raising=False)
    monkeypatch.setenv("CHAMELEON_ENV", "production")
    with pytest.raises(CryptoNotConfigured):
        init_crypto()


def test_init_crypto_dev_default(monkeypatch):
    """dev 模式 + 无 key → 自动设 demo key，可用"""
    monkeypatch.delenv("CHAMELEON_CRYPTO_KEY", raising=False)
    monkeypatch.delenv("CHAMELEON_ENV", raising=False)
    init_crypto()
    assert os.environ.get("CHAMELEON_CRYPTO_KEY")
    # 用 demo key 能正常加解密
    ct = encrypt("smoke")
    assert decrypt(ct) == "smoke"


def test_init_crypto_idempotent(monkeypatch):
    """已设 key 时 init_crypto 不动它"""
    real_key = _gen_key_b64()
    monkeypatch.setenv("CHAMELEON_CRYPTO_KEY", real_key)
    init_crypto()
    assert os.environ["CHAMELEON_CRYPTO_KEY"] == real_key
