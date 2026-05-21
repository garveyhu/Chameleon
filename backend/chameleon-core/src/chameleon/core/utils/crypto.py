"""敏感数据加密（仿 sage crypto_util）

AES-256-GCM 对称加密。加密后带 "ENC:" 前缀便于识别。
密钥从环境变量 `CHAMELEON_CRYPTO_KEY`（base64 32 字节）读取。

用途：把外部 agent api_key 等存 DB 时加密；读出时 get_or_decrypt 自动解。

v1 不强制使用——可选能力。
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENC_PREFIX = "ENC:"
_NONCE_LEN = 12


class CryptoNotConfigured(Exception):
    """CHAMELEON_CRYPTO_KEY 未配置"""


def _get_key() -> bytes:
    raw = os.environ.get("CHAMELEON_CRYPTO_KEY")
    if not raw:
        raise CryptoNotConfigured(
            "CHAMELEON_CRYPTO_KEY 未设置；生成方法：python -c "
            "'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
        )
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as e:
        raise CryptoNotConfigured(f"CHAMELEON_CRYPTO_KEY 非合法 base64: {e}") from e
    if len(key) not in (16, 24, 32):
        raise CryptoNotConfigured(
            f"CHAMELEON_CRYPTO_KEY 长度 {len(key)} 字节，需 16/24/32"
        )
    return key


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt(plaintext: str) -> str:
    """加密；返 `ENC:<base64(nonce + ciphertext)>`"""
    key = _get_key()
    nonce = os.urandom(_NONCE_LEN)
    aes = AESGCM(key)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return f"{_ENC_PREFIX}{blob}"


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        raise ValueError("not an encrypted value")
    blob = base64.urlsafe_b64decode(value[len(_ENC_PREFIX) :])
    nonce = blob[:_NONCE_LEN]
    ct = blob[_NONCE_LEN:]
    aes = AESGCM(_get_key())
    return aes.decrypt(nonce, ct, None).decode("utf-8")


def get_or_decrypt(value: str | None) -> str | None:
    """智能：已加密的解密，未加密的原样返回"""
    if value is None:
        return None
    return decrypt(value) if is_encrypted(value) else value
