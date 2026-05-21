"""密码哈希（argon2id）

OWASP 2023+ 推荐密码哈希算法。包格式：
  $argon2id$v=19$m=65536,t=2,p=1$<salt>$<hash>

参数选型（参考 OWASP Cheat Sheet）：
- memory_cost = 64 MiB     抵御 GPU / ASIC
- time_cost   = 2 迭代次数  权衡性能：单次 hash ≈ 50ms 在普通服务器
- parallelism = 1           容器化部署友好

每次 hash 用新随机盐 → 同明文 hash 两次结果不同；verify 时盐从 hash 串里读。
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=64 * 1024,  # KiB → 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    """argon2id 哈希一段明文密码

    返回完整 modular crypt format 字符串（含算法版本 / 参数 / 盐 / 哈希）。
    """
    if not isinstance(plain, str):
        raise TypeError("plain password must be str")
    if not plain:
        raise ValueError("plain password is empty")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文与哈希是否匹配；不抛异常，返回 bool。"""
    if not plain or not hashed:
        return False
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """参数迭代后旧 hash 是否需要重新生成；下次用户登录时检测。"""
    try:
        return _hasher.check_needs_rehash(hashed)
    except Exception:
        return False
