"""P20.2 PR #48: Ed25519 manifest signing 单元"""

from __future__ import annotations

import base64

import pytest

from chameleon.core.plugins.signing import (
    InvalidSignatureError,
    generate_keypair,
    sign_manifest,
    verify_manifest,
)


def test_roundtrip_sign_verify():
    kp = generate_keypair()
    payload = b'{"name":"x","version":"1.0.0","type":"tool","entrypoint":"a.b:C"}'
    sig = sign_manifest(payload, kp.private_key_b64)
    # 不抛 = 通过
    verify_manifest(payload, signature_b64=sig, public_key=kp.public_key_b64)


def test_verify_supports_ed25519_prefix():
    kp = generate_keypair()
    payload = b"hello"
    sig = sign_manifest(payload, kp.private_key_b64)
    verify_manifest(
        payload,
        signature_b64=sig,
        public_key=kp.public_key_pinning,  # "ed25519:<b64>"
    )


def test_tampered_manifest_rejected():
    kp = generate_keypair()
    payload = b'{"a":1}'
    sig = sign_manifest(payload, kp.private_key_b64)
    with pytest.raises(InvalidSignatureError, match="不匹配"):
        verify_manifest(
            payload + b" tampered",
            signature_b64=sig,
            public_key=kp.public_key_b64,
        )


def test_wrong_public_key_rejected():
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    payload = b"hello"
    sig = sign_manifest(payload, kp1.private_key_b64)
    with pytest.raises(InvalidSignatureError):
        verify_manifest(
            payload, signature_b64=sig, public_key=kp2.public_key_b64
        )


def test_empty_signature_rejected():
    kp = generate_keypair()
    with pytest.raises(InvalidSignatureError, match="缺少签名"):
        verify_manifest(b"x", signature_b64="", public_key=kp.public_key_b64)


def test_empty_pubkey_rejected():
    kp = generate_keypair()
    sig = sign_manifest(b"x", kp.private_key_b64)
    with pytest.raises(InvalidSignatureError, match="公钥"):
        verify_manifest(b"x", signature_b64=sig, public_key="")


def test_bad_signature_length_rejected():
    kp = generate_keypair()
    bad_sig = base64.b64encode(b"too-short").decode()
    with pytest.raises(InvalidSignatureError, match="64 字节"):
        verify_manifest(b"x", signature_b64=bad_sig, public_key=kp.public_key_b64)


def test_bad_pubkey_length_rejected():
    kp = generate_keypair()
    sig = sign_manifest(b"x", kp.private_key_b64)
    bad_pk = base64.b64encode(b"too-short").decode()
    with pytest.raises(InvalidSignatureError, match="32 字节"):
        verify_manifest(b"x", signature_b64=sig, public_key=bad_pk)


def test_invalid_base64_rejected():
    kp = generate_keypair()
    with pytest.raises(InvalidSignatureError, match="base64"):
        verify_manifest(
            b"x",
            signature_b64="!!!not-base64!!!",
            public_key=kp.public_key_b64,
        )
