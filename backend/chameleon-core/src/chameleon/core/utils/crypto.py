"""敏感数据加密（仿 sage crypto_util）

AES-256-GCM 对称加密。加密后带 "ENC:" 前缀便于识别。
密钥从环境变量 `CHAMELEON_CRYPTO_KEY`（base64 32 字节）读取。

用途：把 providers.api_key / 第三方平台 token 等敏感字段存 DB 时加密；
读出时 get_or_decrypt 自动解。

启动期初始化（init_crypto）行为：
- production 环境（CHAMELEON_ENV=production）且无 key → fail-fast
- 非 production 且无 key → 设固定 demo key + warn 日志（一次性）
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

_ENC_PREFIX = "ENC:"
_NONCE_LEN = 12

# 仅 dev / test 用：固定 32 字节 demo key（sha256("chameleon-dev-fixed-demo") 的 base64）
# 永远不要在生产用此 key；production 必须显式设置 CHAMELEON_CRYPTO_KEY
_DEMO_KEY_B64 = "aZRDaXpXZW5DJrioX-iVAzYwzgI-LGjrlvoQ_lr5tCI="


class CryptoNotConfigured(Exception):
    """CHAMELEON_CRYPTO_KEY 未配置或非法"""


def init_crypto() -> None:
    """启动期调用。production 缺 key fail-fast；dev 缺 key 用 demo key + warn。

    幂等：已设置 key 时不动；多次调用安全。
    """
    if os.environ.get("CHAMELEON_CRYPTO_KEY"):
        return

    env = os.environ.get("CHAMELEON_ENV", "").lower()
    if env == "production":
        raise CryptoNotConfigured(
            "production 环境必须设置 CHAMELEON_CRYPTO_KEY；生成方法：\n"
            "  python -c 'import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'"
        )

    os.environ["CHAMELEON_CRYPTO_KEY"] = _DEMO_KEY_B64
    logger.warning(
        "CHAMELEON_CRYPTO_KEY 未设置，已使用 dev demo key（仅限开发！"
        "生产部署必须设 CHAMELEON_ENV=production 与真实 key）"
    )


def _get_key() -> bytes:
    raw = os.environ.get("CHAMELEON_CRYPTO_KEY")
    if not raw:
        raise CryptoNotConfigured(
            "CHAMELEON_CRYPTO_KEY 未设置；启动前调用 init_crypto() 或显式设置 env"
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
