"""雪花 ID 单测（含高并发场景）"""

from __future__ import annotations

import threading

import pytest

from chameleon.data.utils.snowflake import (
    _MAX_INSTANCE,
    _Snowflake,
    next_id,
    next_session_id,
)


def test_next_id_returns_int():
    a = next_id()
    assert isinstance(a, int)
    assert a > 0


def test_next_id_monotonic_increasing():
    """同实例连续 ID 必须严格递增"""
    ids = [next_id() for _ in range(1000)]
    for prev, curr in zip(ids, ids[1:], strict=False):
        assert curr > prev


def test_next_id_uniqueness_in_burst():
    """短时间内大量 ID 必须全部唯一（单线程，序列号位足够）"""
    ids = {next_id() for _ in range(10000)}
    assert len(ids) == 10000


def test_next_id_concurrent_uniqueness():
    """多线程并发产 ID 必须全部唯一"""
    sf = _Snowflake(instance_id=1)
    n_threads = 16
    per_thread = 1000
    results: list[int] = []
    lock = threading.Lock()

    def worker():
        local = [sf.next_id() for _ in range(per_thread)]
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == n_threads * per_thread
    assert len(set(results)) == n_threads * per_thread


def test_instance_id_out_of_range_raises():
    with pytest.raises(ValueError):
        _Snowflake(instance_id=-1)
    with pytest.raises(ValueError):
        _Snowflake(instance_id=_MAX_INSTANCE + 1)


def test_instance_id_boundaries_ok():
    _Snowflake(instance_id=0)
    _Snowflake(instance_id=_MAX_INSTANCE)


def test_different_instance_ids_yield_different_ids():
    """同毫秒不同 instance_id 产生不同 ID（前提：instance_id 位真的写入了）"""
    a = _Snowflake(instance_id=0)
    b = _Snowflake(instance_id=42)
    ids_a = {a.next_id() for _ in range(100)}
    ids_b = {b.next_id() for _ in range(100)}
    # 两组 ID 应该完全不交集
    assert ids_a.isdisjoint(ids_b)


def test_id_64bit_bounded():
    """ID 必须在 63 bit 范围（最高位是符号位）"""
    for _ in range(100):
        sid = next_id()
        assert 0 < sid < (1 << 63)


def test_next_session_id_format():
    """sess_ 前缀 + base32 编码"""
    sid = next_session_id()
    assert sid.startswith("sess_")
    body = sid[len("sess_"):]
    assert body
    # base32 字符集（去 padding 后）
    assert all(c in "abcdefghijklmnopqrstuvwxyz234567" for c in body), body


def test_next_session_id_uniqueness():
    sids = {next_session_id() for _ in range(1000)}
    assert len(sids) == 1000
