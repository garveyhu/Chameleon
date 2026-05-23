"""Ed25519 manifest 签名 / 验签 —— P20.2 PR #48

设计：
- registry index 列每个 publisher 的公钥（pinning）；安装时按 publisher name
  查 pinned pubkey + 用它验 manifest 签名
- 签名格式：detached signature 64 字节，二进制 + base64 wire 形态
- 红线（plan §2 P20）：manifest 远程拉必须验签，陌生签名一律拒绝
"""

from __future__ import annotations

import base64
from dataclasses import dataclass


def _decode(value: str, *, expected_prefix: str = "") -> bytes:
    """支持 'ed25519:<b64>' 或纯 base64 形态；返回 raw bytes"""
    if expected_prefix and value.startswith(expected_prefix + ":"):
        value = value[len(expected_prefix) + 1 :]
    try:
        return base64.b64decode(value, validate=True)
    except Exception as e:
        raise InvalidSignatureError(f"非法 base64: {e}") from e


class InvalidSignatureError(Exception):
    """签名校验失败（公钥不对 / 数据被篡改 / 格式错）"""


@dataclass(frozen=True)
class Keypair:
    """开发 / 测试用 keypair 容器"""

    public_key_b64: str
    private_key_b64: str

    @property
    def public_key_pinning(self) -> str:
        """registry index 里 pin 的格式：ed25519:<b64>"""
        return f"ed25519:{self.public_key_b64}"


def generate_keypair() -> Keypair:
    """生成新 Ed25519 keypair —— admin 发布插件前一次性生成，私钥自管"""
    from nacl import signing

    key = signing.SigningKey.generate()
    return Keypair(
        public_key_b64=base64.b64encode(bytes(key.verify_key)).decode("ascii"),
        private_key_b64=base64.b64encode(bytes(key)).decode("ascii"),
    )


def sign_manifest(manifest_bytes: bytes, private_key_b64: str) -> str:
    """对 manifest_bytes 签名；返 base64 编码的 64 字节签名"""
    from nacl import signing

    raw_key = _decode(private_key_b64)
    sk = signing.SigningKey(raw_key)
    sig = sk.sign(manifest_bytes).signature
    return base64.b64encode(sig).decode("ascii")


def verify_manifest(
    manifest_bytes: bytes,
    *,
    signature_b64: str,
    public_key: str,
) -> None:
    """验证签名；不通过 raise InvalidSignatureError。

    Args:
        manifest_bytes: 原始 manifest 字节流（按 wire 拿到的原文，不能 re-format）
        signature_b64: base64 detached signature（64 字节）
        public_key: registry 里 pinning 的 publisher 公钥，
            支持 'ed25519:<b64>' 或纯 b64
    """
    from nacl import exceptions as nacl_exc
    from nacl import signing

    if not signature_b64:
        raise InvalidSignatureError("缺少签名")
    if not public_key:
        raise InvalidSignatureError("缺少 publisher 公钥（registry index 未 pin）")

    sig_raw = _decode(signature_b64)
    pubkey_raw = _decode(public_key, expected_prefix="ed25519")

    if len(sig_raw) != 64:
        raise InvalidSignatureError(
            f"Ed25519 签名应 64 字节，当前 {len(sig_raw)}"
        )
    if len(pubkey_raw) != 32:
        raise InvalidSignatureError(
            f"Ed25519 公钥应 32 字节，当前 {len(pubkey_raw)}"
        )

    vk = signing.VerifyKey(pubkey_raw)
    try:
        vk.verify(manifest_bytes, sig_raw)
    except nacl_exc.BadSignatureError as e:
        raise InvalidSignatureError("签名与数据/公钥不匹配") from e


__all__ = [
    "InvalidSignatureError",
    "Keypair",
    "generate_keypair",
    "sign_manifest",
    "verify_manifest",
]
