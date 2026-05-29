"""argon2id 密码哈希单测"""

from __future__ import annotations

import pytest

from chameleon.data.utils.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)


def test_hash_password_returns_argon2_format():
    """格式：$argon2id$v=19$m=65536,t=2,p=1$<salt>$<hash>"""
    h = hash_password("secret-pwd-123")
    assert h.startswith("$argon2id$")
    assert "m=65536" in h  # memory_cost 64 MiB
    assert "t=2" in h  # time_cost
    assert "p=1" in h  # parallelism


def test_hash_same_password_yields_different_results():
    """随机盐 → 同明文 hash 两次结果不同"""
    p = "secret"
    h1 = hash_password(p)
    h2 = hash_password(p)
    assert h1 != h2


def test_verify_correct_password():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", h) is True


def test_verify_wrong_password():
    h = hash_password("right-password")
    assert verify_password("wrong-password", h) is False


def test_verify_empty_inputs_return_false():
    assert verify_password("", "x") is False
    assert verify_password("x", "") is False
    assert verify_password("", "") is False


def test_verify_malformed_hash_returns_false():
    """乱码 hash 不抛异常"""
    assert verify_password("any", "not-a-real-hash") is False


def test_hash_empty_raises():
    with pytest.raises(ValueError):
        hash_password("")


def test_hash_non_str_raises():
    with pytest.raises(TypeError):
        hash_password(b"bytes")  # type: ignore[arg-type]


def test_needs_rehash_returns_bool():
    h = hash_password("x")
    assert isinstance(needs_rehash(h), bool)
    assert needs_rehash("not-a-real-hash") is False
