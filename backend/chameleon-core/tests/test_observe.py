"""chameleon.core.observe 单测

覆盖：
- observe context manager 栈语义
- contextvar 自动 parent_id 传递（嵌套时）
- 显式 parent_id 覆盖
- 显式 request_id 用法
- 退出后 contextvar 恢复
- async 并发隔离（不同 task 不共享）
"""

from __future__ import annotations

import asyncio

from chameleon.core.observe import (
    ObservationType,
    current_observation_id,
    observe,
)

# ── 基本语义 ──────────────────────────────────────────────


async def test_outer_no_parent():
    assert current_observation_id() is None
    async with observe(request_id="r1") as o:
        assert o.request_id == "r1"
        assert o.parent_id is None
        assert current_observation_id() == "r1"
    assert current_observation_id() is None


async def test_nested_auto_parent():
    async with observe(request_id="root") as outer:
        assert outer.parent_id is None
        async with observe(request_id="child") as inner:
            assert inner.request_id == "child"
            assert inner.parent_id == "root"
            assert current_observation_id() == "child"
        # 内层退出后恢复 outer
        assert current_observation_id() == "root"
    assert current_observation_id() is None


async def test_three_level_nesting():
    async with observe(request_id="a"):
        async with observe(request_id="b") as b:
            assert b.parent_id == "a"
            async with observe(request_id="c") as c:
                assert c.parent_id == "b"
            assert current_observation_id() == "b"
        assert current_observation_id() == "a"


async def test_explicit_parent_overrides():
    async with observe(request_id="root"):
        async with observe(request_id="child", parent_id="external") as c:
            assert c.parent_id == "external"


async def test_auto_request_id_uniqueness():
    """不传 request_id 时自动生成 uuid"""
    ids = []
    for _ in range(5):
        async with observe() as o:
            ids.append(o.request_id)
    assert len(set(ids)) == 5


# ── observation_type ──────────────────────────────────────


async def test_observation_type_default():
    async with observe() as o:
        assert o.observation_type == "generation"


async def test_observation_type_enum():
    async with observe(observation_type=ObservationType.TOOL) as o:
        assert o.observation_type == "tool"


async def test_observation_type_string():
    async with observe(observation_type="retriever") as o:
        assert o.observation_type == "retriever"


# ── meta ──────────────────────────────────────────────────


async def test_meta_isolated_per_observation():
    """meta dict 是 per-observation，不共享"""
    async with observe(request_id="a") as a:
        a.meta["x"] = 1
        async with observe(request_id="b") as b:
            b.meta["x"] = 2
            assert b.meta["x"] == 2
        # 外层 meta 不受影响
        assert a.meta["x"] == 1


# ── 异常路径 ──────────────────────────────────────────────


async def test_contextvar_restored_on_exception():
    """observe 块内抛异常时 contextvar 仍应恢复"""
    async with observe(request_id="a"):
        try:
            async with observe(request_id="b"):
                raise RuntimeError("kaboom")
        except RuntimeError:
            pass
        # 内层退出（异常）后仍能拿到外层
        assert current_observation_id() == "a"
    assert current_observation_id() is None


# ── 并发隔离 ──────────────────────────────────────────────


async def test_concurrent_tasks_isolated():
    """asyncio.gather 多 task contextvar 各自独立"""

    async def task(name: str) -> str | None:
        async with observe(request_id=name):
            await asyncio.sleep(0.01)
            return current_observation_id()

    results = await asyncio.gather(*(task(f"r{i}") for i in range(5)))
    assert results == ["r0", "r1", "r2", "r3", "r4"]
    assert current_observation_id() is None
