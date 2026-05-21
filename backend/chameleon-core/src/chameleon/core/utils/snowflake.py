"""雪花 ID 生成器（裁决 A11）

64-bit 结构（与 Twitter 雪花对齐）：
  1 bit  - 符号位（0）
  41 bit - 时间戳（毫秒，相对 epoch）
  10 bit - 机器号（instance_id，env CHAMELEON_INSTANCE_ID）
  12 bit - 序列号（同一毫秒内）

线程安全（用 threading.Lock）。每毫秒最多 4096 个 ID。
"""

from __future__ import annotations

import base64
import threading
import time

from chameleon.core.config import inventory

# epoch = 2026-01-01 00:00:00 UTC
_EPOCH_MS = 1767225600000

_INSTANCE_BITS = 10
_SEQUENCE_BITS = 12
_MAX_INSTANCE = (1 << _INSTANCE_BITS) - 1
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1


class _Snowflake:
    def __init__(self, instance_id: int) -> None:
        if not 0 <= instance_id <= _MAX_INSTANCE:
            raise ValueError(
                f"instance_id out of range [0, {_MAX_INSTANCE}]: {instance_id}"
            )
        self.instance_id = instance_id
        self._last_ms = -1
        self._seq = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            now_ms = int(time.time() * 1000)
            if now_ms == self._last_ms:
                self._seq = (self._seq + 1) & _MAX_SEQUENCE
                if self._seq == 0:
                    # 序列耗尽，等到下一毫秒
                    while now_ms <= self._last_ms:
                        now_ms = int(time.time() * 1000)
            else:
                self._seq = 0
            self._last_ms = now_ms

            return (
                ((now_ms - _EPOCH_MS) << (_INSTANCE_BITS + _SEQUENCE_BITS))
                | (self.instance_id << _SEQUENCE_BITS)
                | self._seq
            )


_DEFAULT: _Snowflake | None = None


def _default() -> _Snowflake:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = _Snowflake(inventory.chameleon_instance_id())
    return _DEFAULT


def next_id() -> int:
    """生成下一个雪花 ID（int）"""
    return _default().next_id()


def next_session_id() -> str:
    """生成会话 ID：sess_ + base32 编码雪花

    格式比裸 int 友好（短、URL safe、不含 0/O 易混字符——base32 默认含但勉强可接受）
    """
    raw = next_id()
    # 转 8 字节 big-endian + base32（去 padding）
    b = raw.to_bytes(8, "big", signed=False)
    encoded = base64.b32encode(b).decode("ascii").rstrip("=").lower()
    return f"sess_{encoded}"
